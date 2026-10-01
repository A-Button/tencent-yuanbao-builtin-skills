"""
在 AF_UNIX 套接字可能被禁用的环境（如沙箱虚拟机）中运行 LibreOffice (soffice) 的辅助模块。
运行时自动检测限制，并在需要时通过 LD_PRELOAD 注入垫片共享库来绕过。

用法:
    from office.soffice import run_soffice, get_soffice_env

    # 方式一 - 直接运行 soffice
    result = run_soffice(["--headless", "--convert-to", "pdf", "input.pptx"])

    # 方式二 - 获取环境变量字典，自行调用子进程
    env = get_soffice_env()
    subprocess.run(["soffice", ...], env=env)
"""

import os
import socket
import subprocess
import tempfile
from pathlib import Path

_SHIM_SO: Path = Path(tempfile.gettempdir()) / "lo_socket_shim.so"


def _requires_socket_shim() -> bool:
    """探测当前系统是否阻止了 AF_UNIX 套接字的创建。"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.close()
    except OSError:
        return True
    return False


def _build_shim_if_needed() -> Path:
    """如果垫片共享库尚未编译，则编译并返回其路径。"""
    if _SHIM_SO.exists():
        return _SHIM_SO

    tmp_dir = Path(tempfile.gettempdir())
    c_source = tmp_dir / "lo_socket_shim.c"
    c_source.write_text(_SHIM_SOURCE)

    try:
        subprocess.run(
            ["gcc", "-shared", "-fPIC", "-o", str(_SHIM_SO), str(c_source), "-ldl"],
            check=True,
            capture_output=True,
        )
    finally:
        c_source.unlink(missing_ok=True)

    return _SHIM_SO


def get_soffice_env() -> dict:
    """构建运行 soffice 所需的环境变量字典，按需注入套接字垫片。"""
    env = os.environ.copy()
    env["SAL_USE_VCLPLUGIN"] = "svp"

    if _requires_socket_shim():
        shim_path = _build_shim_if_needed()
        env["LD_PRELOAD"] = str(shim_path)

    return env


def run_soffice(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """以正确的环境变量启动 soffice 子进程。"""
    env = get_soffice_env()
    cmd = ["soffice"] + args
    return subprocess.run(cmd, env=env, **kwargs)


_SHIM_SOURCE = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static int (*real_socket)(int, int, int);
static int (*real_socketpair)(int, int, int, int[2]);
static int (*real_listen)(int, int);
static int (*real_accept)(int, struct sockaddr *, socklen_t *);
static int (*real_close)(int);
static int (*real_read)(int, void *, size_t);

/* Per-FD bookkeeping (FDs >= 1024 are passed through unshimmed). */
static int is_shimmed[1024];
static int peer_of[1024];
static int wake_r[1024];            /* accept() blocks reading this */
static int wake_w[1024];            /* close()  writes to this      */
static int listener_fd = -1;        /* FD that received listen()    */

__attribute__((constructor))
static void init(void) {
    real_socket     = dlsym(RTLD_NEXT, "socket");
    real_socketpair = dlsym(RTLD_NEXT, "socketpair");
    real_listen     = dlsym(RTLD_NEXT, "listen");
    real_accept     = dlsym(RTLD_NEXT, "accept");
    real_close      = dlsym(RTLD_NEXT, "close");
    real_read       = dlsym(RTLD_NEXT, "read");
    for (int i = 0; i < 1024; i++) {
        peer_of[i] = -1;
        wake_r[i]  = -1;
        wake_w[i]  = -1;
    }
}

/* ---- socket ---------------------------------------------------------- */
int socket(int domain, int type, int protocol) {
    if (domain == AF_UNIX) {
        int fd = real_socket(domain, type, protocol);
        if (fd >= 0) return fd;
        /* socket(AF_UNIX) blocked – fall back to socketpair(). */
        int sv[2];
        if (real_socketpair(domain, type, protocol, sv) == 0) {
            if (sv[0] >= 0 && sv[0] < 1024) {
                is_shimmed[sv[0]] = 1;
                peer_of[sv[0]]    = sv[1];
                int wp[2];
                if (pipe(wp) == 0) {
                    wake_r[sv[0]] = wp[0];
                    wake_w[sv[0]] = wp[1];
                }
            }
            return sv[0];
        }
        errno = EPERM;
        return -1;
    }
    return real_socket(domain, type, protocol);
}

/* ---- listen ---------------------------------------------------------- */
int listen(int sockfd, int backlog) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        listener_fd = sockfd;
        return 0;
    }
    return real_listen(sockfd, backlog);
}

/* ---- accept ---------------------------------------------------------- */
int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        /* Block until close() writes to the wake pipe. */
        if (wake_r[sockfd] >= 0) {
            char buf;
            real_read(wake_r[sockfd], &buf, 1);
        }
        errno = ECONNABORTED;
        return -1;
    }
    return real_accept(sockfd, addr, addrlen);
}

/* ---- close ----------------------------------------------------------- */
int close(int fd) {
    if (fd >= 0 && fd < 1024 && is_shimmed[fd]) {
        int was_listener = (fd == listener_fd);
        is_shimmed[fd] = 0;

        if (wake_w[fd] >= 0) {              /* unblock accept() */
            char c = 0;
            write(wake_w[fd], &c, 1);
            real_close(wake_w[fd]);
            wake_w[fd] = -1;
        }
        if (wake_r[fd] >= 0) { real_close(wake_r[fd]); wake_r[fd]  = -1; }
        if (peer_of[fd] >= 0) { real_close(peer_of[fd]); peer_of[fd] = -1; }

        if (was_listener)
            _exit(0);                        /* conversion done – exit */
    }
    return real_close(fd);
}
"""


if __name__ == "__main__":
    import sys

    result = run_soffice(sys.argv[1:])
    raise SystemExit(result.returncode)
