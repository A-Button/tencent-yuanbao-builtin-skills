#!/usr/bin/env python3
"""完成今日训练：把整场训练标记为已完成。

不连带勾掉剩下的动作——「这场练完了」和「每个动作都做了」是两件事，月历上
显示的完成与否看的是这里的 status，动作勾选保留用户真实的记录。
全部动作勾完时 complete_exercise 会自动收场，这个工具只在「没做完也算今天练完」时用。
不给 session_id 就是今天那一场。
"""

from __future__ import annotations

from _store import Store, run, session_for, touch


def complete_session(args: dict, store: Store) -> dict:
    session = session_for(store, args)
    session["status"] = "done"
    store.replace_session(touch(session))
    return {"date": session["date"], "session_id": session["id"]}


if __name__ == "__main__":
    raise SystemExit(run(complete_session))
