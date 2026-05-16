#!/usr/bin/env python3
"""
ZuJuan API Client - Command Line Interface

Usage:
  python main.py login              # QR code login
  python main.py status             # Check login status
  python main.py search <zsd_id>    # Search questions
  python main.py tree [keyword]     # Browse knowledge tree
  python main.py answer <qid>       # Get answer image

Examples:
  python main.py login
  python main.py search zsd27942 -t t1 -d d3 -l 5
  python main.py search zsd27942 -t t2 -d d4 -y 2025 -l 3
  python main.py tree 函数
  python main.py answer 32801513
"""

import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from client import ZuJuanClient
from knowledge_tree import parse_knowledge_tree, search_tree, flatten_tree


def cmd_login(args):
    """Interactive QR code login."""
    client = ZuJuanClient(grade='high')
    ok = client.login(interactive=True)
    if ok:
        print(f"\nLogin successful! Username: {client.username}")
    else:
        print("\nLogin failed or timed out.")
        sys.exit(1)


def cmd_status(args):
    """Check login status."""
    client = ZuJuanClient(grade='high')
    logged_in = client.is_logged_in()
    print(f"Login status: {'logged in' if logged_in else 'not logged in'}")
    if logged_in:
        print(f"Username: {client.username}")


def cmd_search(args):
    """Search for questions."""
    client = ZuJuanClient(grade=args.grade)

    if args.login:
        client.login(interactive=True)

    result = client.search(
        knowledge_id=args.knowledge_id,
        qtype=args.type,
        difficulty=args.difficulty,
        year=args.year,
        order=args.order,
        page=args.page,
        limit=args.limit,
        multi_count=args.multi_count,
        fill_count=args.fill_count,
    )

    if 'error' in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {args.output}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Knowledge Point: {result['knowledge_id']}")
    print(f"Total Questions: {result['total']}")
    print(f"Returned: {result['count']}")
    print(f"URL: {result['url']}")
    print(f"{'='*60}\n")

    for i, q in enumerate(result['results'], 1):
        print(f"--- Question {i} (ID: {q['id']}) ---")
        print(f"  Source: {q.get('source_text', 'N/A')}")
        print(f"  Type: {q.get('question_type', 'N/A')}")
        print(f"  Difficulty: {q.get('difficulty', 'N/A')} ({q.get('score_rate', 'N/A')})")
        print(f"  Keywords: {', '.join(q.get('knowledge_keywords', []))}")
        print(f"  Tags: {', '.join(q.get('tags', []))}")
        print(f"  Content: {q.get('content_text', '')[:200]}")
        print(f"  Formula Images: {len(q.get('formula_images', []))}")
        print(f"  Detail URL: {q.get('detail_url', '')}")
        print()


def cmd_tree(args):
    """Search or display the knowledge tree."""
    tree = parse_knowledge_tree()

    if args.keyword:
        results = search_tree(tree, args.keyword)
        print(f"Found {len(results)} matches for '{args.keyword}':\n")
        for r in results:
            indent = "  " * r['level']
            print(f"  {indent}{r['name']} ({r['id']})")
    elif args.id:
        # Show node and its children
        flat = flatten_tree(tree)
        target = None
        for node in flat:
            if node['id'] == args.id:
                target = node
                break

        if target:
            print(f"Node: {target['name']} ({target['id']})")
            print(f"Path: {target['path']}")
            # Find direct children
            children = [n for n in flat if n['level'] == target['level'] + 1
                       and n['path'].startswith(target['path'])]
            if children:
                print(f"\nChildren ({len(children)}):")
                for c in children[:50]:
                    indent = "  " * (c['level'] - target['level'])
                    print(f"  {indent}{c['name']} ({c['id']})")
                if len(children) > 50:
                    print(f"  ... and {len(children) - 50} more")
        else:
            print(f"Node {args.id} not found")
    else:
        # Show root topics
        print(f"Knowledge Tree: {len(tree)} root topics, {len(flatten_tree(tree))} total nodes\n")
        for node in tree:
            child_count = len(flatten_tree(node.get('children', [])))
            print(f"  {node['name']} ({node['id']}) - {child_count} descendants")


def cmd_answer(args):
    """Get answer for a question."""
    client = ZuJuanClient(grade='high')
    client.login(interactive=False)  # Load saved cookies

    img_data, content_type = client.get_answer(args.question_id)

    if img_data:
        ext = 'jpg' if content_type and 'jpeg' in content_type else 'png'
        output_path = args.output or f"answer_{args.question_id}.{ext}"
        with open(output_path, 'wb') as f:
            f.write(img_data)
        print(f"Answer saved to {output_path} ({len(img_data)} bytes)")
    else:
        print(f"Could not retrieve answer for question {args.question_id}")
        print("Make sure cookies are saved (run 'login' first or set cookies manually).")


def main():
    parser = argparse.ArgumentParser(
        description='ZuJuan API Client - Search and retrieve exam questions'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # login
    subparsers.add_parser('login', help='QR code WeChat login')

    # status
    subparsers.add_parser('status', help='Check login status')

    # search
    sp = subparsers.add_parser('search', help='Search questions')
    sp.add_argument('knowledge_id', help='Knowledge point ID (e.g., zsd27942)')
    sp.add_argument('-g', '--grade', default='high', choices=['high', 'middle'],
                    help='Grade level')
    sp.add_argument('-t', '--type', choices=['t1', 't2', 't3', 't4'],
                    help='Question type (t1=单选, t2=多选, t3=填空, t4=解答)')
    sp.add_argument('-d', '--difficulty', choices=['d1', 'd2', 'd3', 'd4', 'd5'],
                    help='Difficulty level')
    sp.add_argument('-y', '--year', type=int, help='Year (e.g., 2025)')
    sp.add_argument('-o', '--order', default='latest',
                    choices=['latest', 'hot', 'comprehensive'],
                    help='Sort order')
    sp.add_argument('-p', '--page', type=int, default=1, help='Page number')
    sp.add_argument('-l', '--limit', type=int, default=10,
                    help='Max questions to return')
    sp.add_argument('-mc', '--multi-count', type=int, choices=[2, 3, 4],
                    help='Multi-select answer count')
    sp.add_argument('-fc', '--fill-count', type=int, choices=[1, 2, 3],
                    help='Fill-in-blank count')
    sp.add_argument('--login', action='store_true',
                    help='Also log in (needed for answers)')
    sp.add_argument('--output', '-O', help='Output JSON file path')

    # tree
    tp = subparsers.add_parser('tree', help='Browse knowledge tree')
    tp.add_argument('keyword', nargs='?', help='Search keyword')
    tp.add_argument('--id', help='Show specific node by ID')

    # answer
    ap = subparsers.add_parser('answer', help='Get answer image')
    ap.add_argument('question_id', help='Question ID')
    ap.add_argument('--output', '-O', help='Output image path')

    args = parser.parse_args()

    if args.command == 'login':
        cmd_login(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'search':
        cmd_search(args)
    elif args.command == 'tree':
        cmd_tree(args)
    elif args.command == 'answer':
        cmd_answer(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
