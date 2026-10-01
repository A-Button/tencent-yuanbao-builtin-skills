#!/usr/bin/env python3
"""
iWiki MCP Server 通用客户端脚本

支持连接 MCP Server 并调用任意 tool，以及独立上传文件导入和附件上传

使用方法:
  1. 配置 Token（任选其一）:
     - iwiki-cli auth login                          # OAuth2 授权登录（推荐）
     - iwiki-cli auth save <token>                   # 手动保存 PAT Token
  2. 运行脚本:
     - 列出所有工具: python connect_mcp.py list
     - 调用工具: python connect_mcp.py call <tool_name> [args_json]
     - 从文件读取参数: python connect_mcp.py call <tool_name> --file <json_file>
     - 从 stdin 读取参数: echo '{"docid":"123"}' | python connect_mcp.py call <tool_name> --stdin
     - 上传文件导入: python connect_mcp.py upload <file_path> <parent_id> [options]
     - 上传附件: python connect_mcp.py attach <file_path> <doc_id>
     - 上传图片到多维表格: python connect_mcp.py smartsheet <image_path> <doc_id>

示例:
  python connect_mcp.py list                           # 列出所有可用工具
  python connect_mcp.py call getDocument '{"docid": "4017403457"}'
  python connect_mcp.py call searchDocument '{"query": "项目文档", "offset": 20}'
  python connect_mcp.py call aiSearchDocument '{"query": "项目文档", "limit": 5}'
  python connect_mcp.py call metadata '{"docid": "4017403457"}'
  python connect_mcp.py call getSpaceInfoByKey '{"spaceKey": "devcloud"}'

  # 文件上传导入:
  python connect_mcp.py upload ./doc.md 4017403457                     # 上传 Markdown 文件到指定父目录
  python connect_mcp.py upload ./doc.docx 4017403457 --task-type md_import  # 指定任务类型
  python connect_mcp.py upload ./doc.md 4017403457 --no-cover          # 不覆盖同名文档

  # 附件上传（绑定到已有文档）:
  python connect_mcp.py attach ./image.png 4018955627            # 上传图片附件到指定文档
  python connect_mcp.py attach ./report.pdf 4018955627           # 上传 PDF 附件到指定文档

  # 上传图片到多维表格:
  python connect_mcp.py smartsheet ./image.png 4019549905

MCP Server URL: https://prod.mcp.it.woa.com/app_iwiki_mcp/mcp3
"""

import os
import sys
import json
import io
import mimetypes
import uuid
import time
import warnings

# 抑制 urllib3 的 OpenSSL 警告
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import requests
from typing import Optional, Any
from urllib.parse import quote as url_quote

# 确保 stdout/stderr 使用 UTF-8 编码（解决 Windows GBK 环境下 emoji 输出报错）
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# MCP Server 配置
MCP_URL = "https://prod.mcp.it.woa.com/app_iwiki_mcp/mcp3"
# 文件上传导入端点（与 MCP Server 同源的 HTTP 端点）
IMPORT_URL = "https://prod.mcp.it.woa.com/app_iwiki_mcp/import"


def parse_tool_args(argv_remaining: list) -> dict:
    """
    从命令行参数、文件或 stdin 解析工具调用参数。
    
    支持三种模式:
      1. 直接 JSON 字符串:  '{"key": "value"}'
      2. 从文件读取:        --file <path.json>
      3. 从 stdin 读取:     --stdin
    
    Args:
        argv_remaining: 工具名之后的剩余命令行参数列表
    
    Returns:
        解析后的参数字典
    """
    if not argv_remaining:
        return {}
    
    flag = argv_remaining[0]
    
    # 模式 2: 从文件读取
    if flag == "--file":
        if len(argv_remaining) < 2:
            print("❌ --file 需要指定 JSON 文件路径")
            sys.exit(1)
        file_path = argv_remaining[1]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 文件不存在: {file_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ 文件 JSON 解析错误: {e}")
            sys.exit(1)
    
    # 模式 3: 从 stdin 读取
    if flag == "--stdin":
        try:
            stdin_data = sys.stdin.read()
            if not stdin_data.strip():
                print("❌ stdin 无数据，请通过管道传入 JSON")
                sys.exit(1)
            return json.loads(stdin_data)
        except json.JSONDecodeError as e:
            print(f"❌ stdin JSON 解析错误: {e}")
            sys.exit(1)
    
    # 模式 1: 直接 JSON 字符串（拼接所有剩余参数，兼容 shell 拆分空格的情况）
    try:
        return json.loads(" ".join(argv_remaining))
    except json.JSONDecodeError as e:
        print(f"❌ 参数 JSON 解析错误: {e}")
        sys.exit(1)


class MCPClient:
    """MCP 客户端，提供通用的工具调用能力"""
    
    def __init__(self, token: str, url: str = MCP_URL):
        self.token = token
        self.url = url
        self.request_id = 0
        self.tools_cache: Optional[list] = None
        self.initialized = False
    
    def _next_request_id(self) -> int:
        """生成下一个请求 ID"""
        self.request_id += 1
        return self.request_id
    
    def _send_request(self, method: str, params: dict = None, extra_headers: dict = None) -> dict:
        if params is None:
            params = {}
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/event-stream"
        }
        
        # 合并额外的请求头
        if extra_headers:
            headers.update(extra_headers)
        
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": method,
            "params": params
        }
        
        response = requests.post(self.url, headers=headers, json=payload, timeout=60)
        
        # 检查 HTTP 状态码
        if response.status_code != 200:
            return {
                "error": {
                    "code": response.status_code,
                    "message": f"HTTP {response.status_code}: {response.text[:500]}"
                }
            }
        
        # 处理 SSE 格式的响应
        content_type = response.headers.get("Content-Type", "")
        content = response.text
        
        if "text/event-stream" in content_type or (
            content.lstrip().startswith("event:") or content.lstrip().startswith("data:")
        ):
            last_parsed = None
            # SSE 可能包含多个事件块，每块以空行分隔
            # 每个事件块内可能有多个 data: 行，需要拼接
            events = content.split("\n\n")
            for event in events:
                data_parts = []
                for line in event.split("\n"):
                    if line.startswith("data:"):
                        data_parts.append(line[5:].strip())
                if data_parts:
                    json_str = "".join(data_parts)
                    if json_str:
                        try:
                            parsed = json.loads(json_str)
                            last_parsed = parsed
                            # 优先返回包含 result 或 error 的 JSON-RPC 响应
                            if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                                return parsed
                        except json.JSONDecodeError:
                            continue
            
            # 回退：返回最后一个成功解析的事件
            if last_parsed is not None:
                return last_parsed
        
        return response.json()
    
    def initialize(self) -> dict:
        """初始化 MCP 连接"""
        response = self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "iwiki-mcp-client",
                    "version": "1.0.0"
                }
            }
        )
        
        if "error" not in response:
            self.initialized = True
        
        return response
    
    def list_tools(self, force_refresh: bool = False) -> list:
        if self.tools_cache and not force_refresh:
            return self.tools_cache
        
        response = self._send_request("tools/list", {})
        
        if "result" in response and "tools" in response["result"]:
            self.tools_cache = response["result"]["tools"]
            return self.tools_cache
        
        return []
    
    def get_tool_info(self, tool_name: str) -> Optional[dict]:
        tools = self.list_tools()
        for tool in tools:
            if tool["name"] == tool_name:
                return tool
        return None
    
    def call_tool(self, tool_name: str, arguments: dict = None, scope: str = None) -> dict:
        if arguments is None:
            arguments = {}
        
        extra_headers = None
        if scope:
            extra_headers = {"x-scope": scope}
        
        return self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments
            },
            extra_headers=extra_headers
        )
    
    def __getattr__(self, name: str):
        """
        动态方法调用，支持 client.tool_name(args) 语法
        
        例如:
            client.getDocument(docid="123")
            client.aiSearchDocument(query="test", limit=5)
        """
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        def tool_caller(**kwargs):
            return self.call_tool(name, kwargs)
        return tool_caller
    
    def upload_attachment(self, file_path: str, doc_id: int) -> dict:
        # 上传附件到 iWiki 文档。
        if not os.path.isfile(file_path):
            return {"success": False, "msg": f"文件不存在: {file_path}"}
        
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            return {"success": False, "msg": f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持 50MB"}
        
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        
        # Step 1: 调用 MCP Tool 获取预签名 URL
        presign_result = self.call_tool("prepareAttachmentUpload", {"doc_id": doc_id}, scope="upload")
        
        # 解析 MCP 响应
        if "error" in presign_result:
            return {"success": False, "msg": f"获取预签名 URL 失败: {presign_result['error']}"}
        
        # 从 MCP 响应中提取数据
        presign_data = None
        if "result" in presign_result and "content" in presign_result["result"]:
            for item in presign_result["result"]["content"]:
                if item.get("type") == "text":
                    try:
                        presign_data = json.loads(item["text"])
                        break
                    except json.JSONDecodeError:
                        continue
        
        if not presign_data:
            return {"success": False, "msg": "无法解析预签名 URL 响应"}
        
        attachment_id = presign_data.get("attachment_id")
        upload_url = presign_data.get("url")
        
        if not attachment_id or not upload_url:
            return {"success": False, "msg": f"预签名 URL 响应缺少必要字段: {presign_data}"}
        
        # Step 2: 上传文件到预签名 URL
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        upload_response = requests.put(
            upload_url,
            data=file_content,
            headers={"Content-Type": content_type},
            timeout=300
        )
        
        if upload_response.status_code not in (200, 201, 204):
            return {
                "success": False,
                "msg": f"上传文件到 COS 失败，HTTP {upload_response.status_code}: {upload_response.text[:500]}"
            }
        
        # Step 3: 通知服务器上传完成
        notify_result = self.call_tool(
            "completeAttachmentUpload",
            {"attachmentid": attachment_id, "filepath": filename},
            scope="upload"
        )
        
        if "error" in notify_result:
            return {"success": False, "msg": f"通知上传完成失败: {notify_result['error']}"}
        
        # 构建返回的附件访问链接
        attachment_url = f"https://iwiki.woa.com/tencent/api/attachments/s3/url?attachmentid={attachment_id}"
        
        return {
            "success": True,
            "filename": filename,
            "attachment_id": attachment_id,
            "url": attachment_url
        }
    
    def download_document_images(self, docid: str, output_dir: str = None) -> dict:
        """
        批量下载文档中的所有图片到本地目录。
        
        Args:
            docid:       文档 ID
            output_dir:  输出目录，默认为 ./iwiki_images/<docid>/
        
        Returns:
            下载结果字典，包含成功和失败的统计信息
        """
        if output_dir is None:
            output_dir = os.path.join(".", "iwiki_images", str(docid))
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # Step 1: 获取文档中的所有图片
        print(f"📥 正在获取文档 {docid} 的图片列表...")
        list_result = self.call_tool("listImages", {"docid": docid})
        
        if "error" in list_result:
            return {"success": False, "msg": f"获取图片列表失败: {list_result['error']}"}
        
        # 解析图片列表
        image_ids = []
        if "result" in list_result and "content" in list_result["result"]:
            for item in list_result["result"]["content"]:
                if item.get("type") == "text":
                    try:
                        data = json.loads(item["text"])
                        if isinstance(data, list):
                            image_ids = data
                        elif isinstance(data, dict) and "images" in data:
                            image_ids = data["images"]
                        break
                    except json.JSONDecodeError:
                        continue
        
        if not image_ids:
            return {"success": True, "msg": "文档中没有图片", "downloaded": 0, "failed": 0}
        
        total = len(image_ids)
        print(f"📋 找到 {total} 张图片，开始下载到: {output_dir}")
        
        # Step 2: 批量下载图片
        downloaded = 0
        failed = 0
        failed_list = []
        
        for idx, attachment_id in enumerate(image_ids, 1):
            try:
                # 获取下载链接
                url_result = self.call_tool("getAttachmentDownloadUrl", {"attachmentid": str(attachment_id)})
                
                if "error" in url_result:
                    print(f"  ❌ [{idx}/{total}] 获取下载链接失败: {attachment_id}")
                    failed += 1
                    failed_list.append({"id": attachment_id, "reason": str(url_result["error"])})
                    continue
                
                # 解析下载 URL
                download_url = None
                if "result" in url_result and "content" in url_result["result"]:
                    for item in url_result["result"]["content"]:
                        if item.get("type") == "text":
                            try:
                                data = json.loads(item["text"])
                                download_url = data.get("url") or data.get("download_url")
                                break
                            except json.JSONDecodeError:
                                continue
                
                if not download_url:
                    print(f"  ❌ [{idx}/{total}] 解析下载链接失败: {attachment_id}")
                    failed += 1
                    failed_list.append({"id": attachment_id, "reason": "无法解析下载链接"})
                    continue
                
                # 下载文件
                response = requests.get(download_url, timeout=60)
                if response.status_code != 200:
                    print(f"  ❌ [{idx}/{total}] 下载失败 (HTTP {response.status_code}): {attachment_id}")
                    failed += 1
                    failed_list.append({"id": attachment_id, "reason": f"HTTP {response.status_code}"})
                    continue
                
                # 确定文件扩展名
                content_type = response.headers.get("Content-Type", "")
                ext = ".jpg"  # 默认
                if "png" in content_type:
                    ext = ".png"
                elif "gif" in content_type:
                    ext = ".gif"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "svg" in content_type:
                    ext = ".svg"
                
                # 保存文件
                filename = f"{attachment_id}{ext}"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(response.content)
                
                file_size_kb = len(response.content) / 1024
                print(f"  ✅ [{idx}/{total}] {filename} ({file_size_kb:.1f}KB)")
                downloaded += 1
                
            except Exception as e:
                print(f"  ❌ [{idx}/{total}] 下载异常: {attachment_id} - {e}")
                failed += 1
                failed_list.append({"id": attachment_id, "reason": str(e)})
        
        # 返回结果
        print(f"\n{'='*60}")
        print(f"📊 下载完成: 成功 {downloaded}/{total}, 失败 {failed}/{total}")
        print(f"📁 保存位置: {os.path.abspath(output_dir)}")
        
        return {
            "success": True,
            "total": total,
            "downloaded": downloaded,
            "failed": failed,
            "failed_list": failed_list if failed_list else None,
            "output_dir": os.path.abspath(output_dir)
        }
    
    def upload_image_to_smartsheet(self, image_path: str, doc_id: int) -> dict:
        """
        上传图片到 iWiki 多维表格，返回 ext 附件信息供后续使用。
        
        完整流程：
        1. 获取 Vika 附件上传的预签名 URL
        2. 上传图片到 COS
        3. 启动 Vika 附件绑定任务
        4. 查询上传结果获取附件信息（ext 内容）
        
        注意：此方法只上传图片并返回附件信息，不会自动更新表格记录。
        需要手动调用 smartsheetUpdateRecords 将返回的 ext 内容写入对应字段。
        
        Args:
            image_path:  本地图片文件路径
            doc_id:      多维表格文档 ID
        
        Returns:
            上传结果字典，包含 ext 附件信息
        """
        if not os.path.isfile(image_path):
            return {"success": False, "msg": f"文件不存在: {image_path}"}
        
        file_size = os.path.getsize(image_path)
        if file_size > 50 * 1024 * 1024:
            return {"success": False, "msg": f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持 50MB"}
        
        filename = os.path.basename(image_path)
        content_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        
        # Step 1: 获取 Vika 附件上传的预签名 URL
        print(f"📋 Step 1: 获取预签名 URL...")
        presign_result = self.call_tool("prepareAttachmentUpload", {"task_type": "vika_attachment_import"})
        
        if "error" in presign_result:
            return {"success": False, "msg": f"获取预签名 URL 失败: {presign_result['error']}"}
        
        # 解析预签名信息
        presign_data = None
        if "result" in presign_result and "content" in presign_result["result"]:
            for item in presign_result["result"]["content"]:
                if item.get("type") == "text":
                    try:
                        presign_data = json.loads(item["text"])
                        break
                    except json.JSONDecodeError:
                        continue
        
        if not presign_data:
            return {"success": False, "msg": "无法解析预签名 URL 响应"}
        
        task_id = presign_data.get("task_id")
        prefix = presign_data.get("prefix")
        upload_url = presign_data.get("url")
        form_data = presign_data.get("form_data", {})
        
        if not task_id or not upload_url or not form_data:
            return {"success": False, "msg": f"预签名响应缺少必要字段: {presign_data}"}
        
        print(f"✅ 获取到 task_id: {task_id}")
        
        # Step 2: 上传图片到 COS
        print(f"📤 Step 2: 上传图片到 COS...")
        cos_key = prefix + filename
        
        # 构建 multipart/form-data
        with open(image_path, "rb") as f:
            file_content = f.read()
        
        files = {"file": (filename, file_content, content_type)}
        upload_response = requests.post(
            upload_url,
            data=form_data,
            files=files,
            timeout=300
        )
        
        if upload_response.status_code not in (200, 201, 204):
            return {
                "success": False,
                "msg": f"上传到 COS 失败，HTTP {upload_response.status_code}: {upload_response.text[:500]}"
            }
        
        print(f"✅ 图片已上传到 COS: {cos_key}")
        
        # Step 3: 启动 Vika 附件绑定任务
        print(f"🔗 Step 3: 启动附件绑定任务...")
        bind_result = self.call_tool(
            "startVikaAttachmentTask",
            {
                "task_id": task_id,
                "doc_id": doc_id,
                "cos_key": cos_key
            },
            scope="gray"
        )
        
        if "error" in bind_result:
            return {"success": False, "msg": f"启动绑定任务失败: {bind_result['error']}"}
        
        print(f"✅ 绑定任务已启动")
        
        # Step 4: 查询上传结果
        print(f"🔍 Step 4: 查询上传结果...")
        time.sleep(1)  # 等待 1 秒让任务完成
        
        result_query = self.call_tool("getVikaAttachmentResult", {"task_id": task_id}, scope="gray")
        
        if "error" in result_query:
            return {"success": False, "msg": f"查询上传结果失败: {result_query['error']}"}
        
        # 解析附件信息
        attachment_info = None
        if "result" in result_query and "content" in result_query["result"]:
            for item in result_query["result"]["content"]:
                if item.get("type") == "text":
                    try:
                        data = json.loads(item["text"])
                        if data.get("success") and data.get("data"):
                            # 从 ext 字段解析附件详细信息
                            ext_str = data["data"][0].get("ext", "{}")
                            attachment_info = json.loads(ext_str)
                            break
                    except json.JSONDecodeError:
                        continue
        
        if not attachment_info:
            return {"success": False, "msg": "无法获取附件信息"}
        
        print(f"✅ 附件信息: {attachment_info['name']} ({attachment_info['width']}x{attachment_info['height']})")
        
        return {
            "success": True,
            "task_id": task_id,
            "ext": attachment_info,
            "doc_id": doc_id,
            "msg": "✅ 图片上传完成！请将 ext 的内容写入对应表格的附件字段。"
        }
    
    def upload_file(
        self,
        file_path: str,
        parent_id: int,
        task_type: str = "md_import",
        cover: bool = True,
        import_url: str = IMPORT_URL,
    ) -> dict:
        """
        上传文件并导入到 iWiki 指定目录。
        
        Args:
            file_path:   本地文件路径
            parent_id:   父文档/目录 ID，文件将导入到该目录下
            task_type:   导入任务类型，默认 'md_import'
            cover:       是否覆盖同名文档，默认 True
            import_url:  导入端点 URL，默认使用 IMPORT_URL
        """
        if not os.path.isfile(file_path):
            return {"success": False, "msg": f"文件不存在: {file_path}"}
        
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            return {"success": False, "msg": f"文件过大 ({file_size / 1024 / 1024:.1f}MB)，最大支持 50MB"}
        
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        boundary = f"iwiki-mcp-{uuid.uuid4().hex}"
        body = io.BytesIO()
        
        def write_text(s: str):
            body.write(s.encode("utf-8"))
        
        # 普通字段 parent_id
        write_text(f"--{boundary}\r\n")
        write_text('Content-Disposition: form-data; name="parent_id"\r\n\r\n')
        write_text(str(parent_id))
        write_text("\r\n")
        
        # 普通字段 task_type
        write_text(f"--{boundary}\r\n")
        write_text('Content-Disposition: form-data; name="task_type"\r\n\r\n')
        write_text(task_type)
        write_text("\r\n")
        
        # 普通字段 cover（小写 true/false）
        if cover is not None:
            write_text(f"--{boundary}\r\n")
            write_text('Content-Disposition: form-data; name="cover"\r\n\r\n')
            write_text("true" if cover else "false")
            write_text("\r\n")
        
        encoded_filename = url_quote(filename, safe='')
    
        with open(file_path, "rb") as f:
            write_text(f"--{boundary}\r\n")
            write_text(
                'Content-Disposition: form-data; name="file"; ' +
                f'filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}\r\n'
            )
            write_text(f"Content-Type: {content_type}\r\n\r\n")
            # 写入文件内容
            body.write(f.read())
            write_text("\r\n")
        
        # 结束边界
        write_text(f"--{boundary}--\r\n")
        
        response = requests.post(
            import_url,
            headers={
                **headers,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            data=body.getvalue(),
            timeout=300,
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"上传文件失败，HTTP {response.status_code}: {response.text[:500]}",
            }
        
        try:
            result = response.json()
            if result.get("success"):
                return {
                    "success": True,
                    "task_id": result.get("task_id"),
                    "task_doc_id": result.get("task_doc_id"),
                    "cos_key": result.get("cos_key"),
                    "parent_id": parent_id,
                    "filename": result.get("filename", filename),
                    "import_result": result.get("import_result"),
                }
            else:
                return {"success": False, "msg": result.get("msg", "未知错误")}
        except json.JSONDecodeError:
            return {"success": False, "msg": f"响应解析失败: {response.text[:500]}"}


def print_tools(tools: list):
    """格式化打印工具列表"""
    print(f"\n📋 可用工具列表 (共 {len(tools)} 个):")
    print("=" * 80)
    
    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "")[:60]
        print(f"  • {name}")
        print(f"    {desc}...")
        
        # 打印参数信息
        if "inputSchema" in tool and "properties" in tool["inputSchema"]:
            props = tool["inputSchema"]["properties"]
            required = tool["inputSchema"].get("required", [])
            if props:
                params = []
                for pname, pinfo in props.items():
                    req_mark = "*" if pname in required else ""
                    params.append(f"{pname}{req_mark}")
                print(f"    参数: {', '.join(params)}")
        print()


def print_tool_detail(tool: dict):
    """打印工具详细信息"""
    print(f"\n📝 工具详情: {tool['name']}")
    print("=" * 80)
    print(f"描述: {tool.get('description', 'N/A')}")
    
    if "inputSchema" in tool and "properties" in tool["inputSchema"]:
        print("\n参数:")
        props = tool["inputSchema"]["properties"]
        required = tool["inputSchema"].get("required", [])
        
        for pname, pinfo in props.items():
            req_mark = " (必填)" if pname in required else " (可选)"
            ptype = pinfo.get("type", "any")
            pdesc = pinfo.get("description", "")
            print(f"  • {pname}{req_mark}")
            print(f"    类型: {ptype}")
            if pdesc:
                print(f"    说明: {pdesc}")


def print_result(result: dict):
    """格式化打印调用结果"""
    if "error" in result:
        print(f"❌ 错误: {result['error']}")
    elif "result" in result:
        res = result["result"]
        if "content" in res and isinstance(res["content"], list):
            for item in res["content"]:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    # 尝试格式化 JSON
                    try:
                        data = json.loads(text)
                        print(json.dumps(data, indent=2, ensure_ascii=False))
                    except json.JSONDecodeError:
                        print(text)
        else:
            print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def print_upload_result(result: dict):
    """格式化打印上传导入结果"""
    print("\n📤 上传导入结果:")
    print("=" * 80)
    
    if result.get("success"):
        print("✅ 导入成功!")
        if "data" in result and result["data"]:
            print(json.dumps(result["data"], indent=2, ensure_ascii=False))
    else:
        print(f"❌ 导入失败: {result.get('msg', '未知错误')}")
        if "data" in result and result["data"]:
            print(json.dumps(result["data"], indent=2, ensure_ascii=False))


def print_attachment_result(result: dict):
    """格式化打印附件上传结果"""
    if result.get("success"):
        print(f"✅ 附件上传成功!")
        print(f"   附件 ID:    {result.get('attachment_id')}")

    else:
        print(f"❌ 附件上传失败: {result.get('msg', '未知错误')}")



def load_token_from_credentials_file():
    """从 ~/.iwiki/credentials (JSON 格式) 读取 token，优先级: oauth_token > pat_token"""
    cred_path = os.environ.get("IWIKI_TOKEN_FILE")
    if not cred_path:
        home = os.path.expanduser("~")
        cred_path = os.path.join(home, ".iwiki", "credentials")

    if not os.path.isfile(cred_path):
        return None

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 优先 oauth_token，其次 pat_token
        return data.get("oauth_token") or data.get("pat_token") or None
    except (json.JSONDecodeError, OSError):
        return None


def load_token_from_env_file():
    """尝试从 .env 文件加载 TAI_PAT_TOKEN 或 IWIKI_TOKEN"""
    env_file_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
    ]
    
    token_keys = ("TAI_PAT_TOKEN=", "IWIKI_TOKEN=")
    
    for env_file in env_file_paths:
        if os.path.isfile(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        for key in token_keys:
                            if line.startswith(key):
                                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if token:
                                    return token
            except Exception:
                continue
    return None


def main():
    # Token 获取优先级：
    # 1. ~/.iwiki/credentials 文件（JSON 格式，与 iwiki-cli 共享）
    # 2. 环境变量 TAI_PAT_TOKEN / IWIKI_TOKEN
    # 3. .env 文件
    token = load_token_from_credentials_file()
    if not token:
        token = os.environ.get("TAI_PAT_TOKEN") or os.environ.get("IWIKI_TOKEN")
    if not token:
        token = load_token_from_env_file()

    if not token:
        print("❌ 错误: 未配置 Token")
        print()
        print("请先登录后再使用，选择以下任一方式:")
        print("  iwiki-cli auth login          # OAuth2 浏览器授权登录（推荐）")
        print("  iwiki-cli auth save <token>   # 手动保存 PAT Token")
        print()
        print("PAT Token 获取地址: https://tai.it.woa.com/user/pat")
        sys.exit(1)
    
    # upload 命令直接走 HTTP 端点，无需初始化 MCP 连接
    if len(sys.argv) > 1 and sys.argv[1].lower() == "upload":
        if len(sys.argv) < 4:
            print("❌ 用法: python connect_mcp.py upload <file_path> <parent_id> [--task-type <type>] [--no-cover]")
            sys.exit(1)
        
        up_file_path = sys.argv[2]
        try:
            up_parent_id = int(sys.argv[3])
        except ValueError:
            print(f"❌ parent_id 必须为整数: {sys.argv[3]}")
            sys.exit(1)
        
        up_task_type = "md_import"
        up_cover = True
        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == "--task-type" and i + 1 < len(sys.argv):
                up_task_type = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--no-cover":
                up_cover = False
                i += 1
            else:
                print(f"❌ 未知选项: {sys.argv[i]}")
                sys.exit(1)
        
        client = MCPClient(token)
        file_size_mb = os.path.getsize(up_file_path) / 1024 / 1024 if os.path.isfile(up_file_path) else 0
        print(f"📁 上传: {up_file_path} ({file_size_mb:.2f}MB) -> parent:{up_parent_id} type:{up_task_type}")
        
        result = client.upload_file(up_file_path, up_parent_id, up_task_type, up_cover)
        print_upload_result(result)
        return
    
    # attach 命令直接走 HTTP 端点，无需初始化 MCP 连接
    if len(sys.argv) > 1 and sys.argv[1].lower() == "attach":
        if len(sys.argv) < 4:
            print("❌ 用法: python connect_mcp.py attach <file_path> <doc_id>")
            print()
            print("说明: 上传附件到已存在的 iWiki 文档")
            print("  file_path:  本地文件路径 (支持图片、PDF 等)")
            print("  doc_id:     目标文档 ID (需先创建文档获取此 ID)")
            sys.exit(1)
        
        att_file_path = sys.argv[2]
        try:
            att_doc_id = int(sys.argv[3])
        except ValueError:
            print(f"❌ doc_id 必须为整数: {sys.argv[3]}")
            sys.exit(1)
        
        client = MCPClient(token)
        file_size_mb = os.path.getsize(att_file_path) / 1024 / 1024 if os.path.isfile(att_file_path) else 0
        print(f"📎 上传: {att_file_path} ({file_size_mb:.2f}MB) -> doc:{att_doc_id}")
        
        result = client.upload_attachment(att_file_path, att_doc_id)
        print_attachment_result(result)
        return
    
    # smartsheet 命令：上传图片到多维表格
    if len(sys.argv) > 1 and sys.argv[1].lower() == "smartsheet":
        if len(sys.argv) < 4:
            print(" 用法: python connect_mcp.py smartsheet <image_path> <doc_id>")
            print()
            print("说明: 上传图片到 iWiki 多维表格（不自动更新记录）")
            print("  image_path:  本地图片文件路径")
            print("  doc_id:      多维表格文档 ID")
            print("  python connect_mcp.py smartsheet ./image.png 4019549905")
            sys.exit(1)
        
        sm_image_path = sys.argv[2]
        try:
            sm_doc_id = int(sys.argv[3])
        except ValueError:
            print(f"❌ doc_id 必须为整数: {sys.argv[3]}")
            sys.exit(1)
        
        client = MCPClient(token)
        file_size_mb = os.path.getsize(sm_image_path) / 1024 / 1024 if os.path.isfile(sm_image_path) else 0
    
        result = client.upload_image_to_smartsheet(sm_image_path, sm_doc_id)
        print(result)
        return
    
    # download 命令需要初始化 MCP 连接
    if len(sys.argv) > 1 and sys.argv[1].lower() == "download":
        if len(sys.argv) < 3:
            print("❌ 用法: python connect_mcp.py download <docid> [--output-dir <path>]")
            print()
            print("说明: 批量下载文档中的所有图片到本地")
            print("  docid:        文档 ID")
            print("  --output-dir: 输出目录 (可选，默认为 ./iwiki_images/<docid>/)")
            print()
            print("示例:")
            print("  python connect_mcp.py download 4017403457")
            print("  python connect_mcp.py download 4017403457 --output-dir ./my_images")
            sys.exit(1)
        
        dl_docid = sys.argv[2]
        dl_output_dir = None
        
        # 解析可选参数
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output-dir" and i + 1 < len(sys.argv):
                dl_output_dir = sys.argv[i + 1]
                i += 2
            else:
                print(f"❌ 未知选项: {sys.argv[i]}")
                sys.exit(1)
        
        client = MCPClient(token)
        # 初始化连接
        init_response = client.initialize()
        if "error" in init_response:
            print(f"❌ 初始化 MCP 连接失败: {init_response['error']}")
            sys.exit(1)
        
        result = client.download_document_images(dl_docid, dl_output_dir)
        
        if not result.get("success"):
            print(f"\n❌ {result.get('msg', '下载失败')}")
            sys.exit(1)
        
        return
    
    # 创建客户端
    client = MCPClient(token)
    
    try:
        # 初始化连接
        init_response = client.initialize()
        
        if "error" in init_response:
            print(f"❌ 初始化失败: {init_response['error']}")
            sys.exit(1)
        
        # 根据命令行参数执行操作
        if len(sys.argv) < 2:
            # 无参数：显示帮助信息
            print("\n❌ 错误: 缺少命令参数\n")
            print("用法:")
            print("  python connect_mcp.py list                                     # 列出所有工具")
            print("  python connect_mcp.py info <tool_name>                         # 查看工具详情")
            print("  python connect_mcp.py call <tool_name> [args_json]             # 调用工具")
            print("  python connect_mcp.py upload <file> <parent_id>                # 上传文件导入")
            print("  python connect_mcp.py attach <file> <doc_id>                   # 上传附件")
            print("  python connect_mcp.py smartsheet <img> <doc>                   # 上传图片到多维表格")
            print("  python connect_mcp.py download <docid> [--output-dir]          # 批量下载文档图片")
            sys.exit(1)
        elif sys.argv[1].lower() == "list":
            # 列出所有工具
            tools = client.list_tools()
            print_tools(tools)
        elif sys.argv[1].lower() == "info" and len(sys.argv) > 2:
            # 查看工具详情
            tool = client.get_tool_info(sys.argv[2])
            if tool:
                print_tool_detail(tool)
            else:
                print(f"❌ 工具 '{sys.argv[2]}' 不存在")
        else:
            # 调用工具：支持 "call <tool> [args]" 和 "<tool> [args]" 两种形式
            if sys.argv[1].lower() == "call" and len(sys.argv) > 2:
                tool_name = sys.argv[2]
                args = parse_tool_args(sys.argv[3:])
            else:
                tool_name = sys.argv[1]
                args = parse_tool_args(sys.argv[2:])
            
            tool = client.get_tool_info(tool_name)
            if not tool:
                print(f"❌ 工具 '{tool_name}' 不存在")
                print("使用 'python connect_mcp.py list' 查看可用工具")
                sys.exit(1)
            
            result = client.call_tool(tool_name, args)
            print_result(result)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
