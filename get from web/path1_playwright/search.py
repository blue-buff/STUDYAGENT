#!/usr/bin/env python3
"""搜索组卷网知识点"""

import argparse
import os
import sqlite3
import sys

DB_PATH = os.path.expanduser("~/.zujuan-scraper/knowledge-tree.db")


def search(query, grade="high", db_path=None):
    """返回 [(id, name, level, parent_id), ...]"""
    conn = sqlite3.connect(db_path or DB_PATH)
    rows = conn.execute(
        "SELECT id, name, level, parent_id FROM knowledge_nodes "
        "WHERE name LIKE ? AND grade = ? ORDER BY level, pos",
        (f"%{query}%", grade)
    ).fetchall()
    conn.close()
    return rows


def get_path(node_id, grade="high", db_path=None):
    """获取节点的完整路径（从根到该节点）"""
    conn = sqlite3.connect(db_path or DB_PATH)
    path = []
    current = conn.execute(
        "SELECT id, name, parent_id, level FROM knowledge_nodes WHERE id = ? AND grade = ?",
        (node_id, grade)
    ).fetchone()
    while current:
        path.insert(0, current)
        if not current[2]:  # parent_id
            break
        current = conn.execute(
            "SELECT id, name, parent_id, level FROM knowledge_nodes WHERE id = ? AND grade = ?",
            (current[2], grade)
        ).fetchone()
    conn.close()
    return path


def main():
    parser = argparse.ArgumentParser(description="搜索组卷网知识点")
    parser.add_argument("query", help="搜索关键词 (如 '函数', '交集')")
    parser.add_argument("-g", "--grade", default="high", choices=["high", "middle"])
    parser.add_argument("-p", "--path", action="store_true", help="显示完整路径")
    parser.add_argument("--db", default=DB_PATH, help="数据库路径")
    args = parser.parse_args()

    results = search(args.query, args.grade, args.db)
    if not results:
        print(f"未找到匹配 '{args.query}' 的知识点")
        sys.exit(1)

    for row in results:
        node_id, name, level, parent_id = row
        indent = "  " * level

        if args.path:
            full_path = get_path(node_id, args.grade, args.db)
            path_str = " > ".join(n[1] for n in full_path)
            print(f"  {node_id}  {path_str}")
        else:
            print(f"  {indent}• {name} ({node_id})")


if __name__ == "__main__":
    main()
