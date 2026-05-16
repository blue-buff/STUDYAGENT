"""
Parse the high school math knowledge tree from KNOWLEDGE_TREE_HIGH.txt
into a structured JSON format.

The text file format uses indentation with special characters:
- • for category nodes with (zsdXXXXX) ID suffix
- Each level deeper indicates a child relationship

Example:
  • 集合与常用逻辑用语 (zsd27926)
    • 集合 (zsd27942)
      • 集合的含义与表示 (zsd27944)
"""

import json
import os
import re
import sys

# Path to the knowledge tree text file
DEFAULT_INPUT = os.path.join(
    os.path.dirname(__file__), '..', 'zujuan', 'KNOWLEDGE_TREE_HIGH.txt'
)
DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(__file__), 'config', 'knowledge_tree_high.json'
)


def parse_knowledge_tree(filepath=None):
    """
    Parse the knowledge tree text file into a hierarchical structure.

    Returns a list of root-level nodes, each with:
        id: str      - Knowledge point ID (e.g., 'zsd27926')
        name: str    - Display name (e.g., '集合与常用逻辑用语')
        level: int   - Depth level (0 = root topic, 1, 2, ...)
        children: [] - Child nodes
    """
    filepath = filepath or DEFAULT_INPUT

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Pattern: • name (zsdXXXXX)
    node_pattern = re.compile(r'^(.*?)(?:•|·)\s+(.+?)\s+\(zsd(\d+)\)\s*$')

    root_nodes = []
    # Stack of (indent_level, node) to track parent relationships
    stack = []

    for line_num, line in enumerate(lines, 1):
        # Skip empty lines and the header
        if not line.strip() or line.startswith('📚') or line.startswith('---'):
            continue

        # Calculate indentation level (first non-whitespace character position)
        stripped = line.lstrip()
        if not stripped:
            continue

        indent = len(line) - len(stripped)
        # Each level is 2 spaces (or 1 tab = 2 spaces equivalent)
        level = indent // 2

        # Try to match node pattern
        match = node_pattern.match(line)
        if match:
            prefix = match.group(1).strip()
            name = match.group(2).strip()
            zsd_id = f"zsd{match.group(3)}"

            node = {
                'id': zsd_id,
                'name': name,
                'level': level,
                'children': [],
            }

            # Find the right parent
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1]['children'].append(node)
            else:
                root_nodes.append(node)

            stack.append((level, node))

    return root_nodes


def flatten_tree(nodes, parent_path=''):
    """Flatten the tree into a list of dicts with path info."""
    result = []
    for node in nodes:
        path = f"{parent_path} > {node['name']}" if parent_path else node['name']
        result.append({
            'id': node['id'],
            'name': node['name'],
            'level': node['level'],
            'path': path,
        })
        if node.get('children'):
            result.extend(flatten_tree(node['children'], path))
    return result


def build_id_map(nodes):
    """Build a flat dict mapping id → node info."""
    id_map = {}

    def _walk(node):
        id_map[node['id']] = {
            'name': node['name'],
            'level': node['level'],
        }
        for child in node.get('children', []):
            _walk(child)

    for n in nodes:
        _walk(n)
    return id_map


def search_tree(nodes, keyword):
    """Search the tree for nodes matching keyword (case-insensitive)."""
    results = []

    def _search(node, path=''):
        current_path = f"{path} > {node['name']}" if path else node['name']
        if keyword.lower() in node['name'].lower():
            results.append({
                'id': node['id'],
                'name': node['name'],
                'level': node['level'],
                'path': current_path,
            })
        for child in node.get('children', []):
            _search(child, current_path)

    for n in nodes:
        _search(n)
    return results


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT

    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Parsing: {input_path}")
    tree = parse_knowledge_tree(input_path)

    # Save tree JSON
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    print(f"Knowledge tree saved to: {output_path}")

    # Save flat index
    flat_path = output_path.replace('.json', '_flat.json')
    flat = flatten_tree(tree)
    with open(flat_path, 'w', encoding='utf-8') as f:
        json.dump(flat, f, ensure_ascii=False, indent=2)
    print(f"Flat index saved to: {flat_path}")

    # Save ID map
    idmap_path = output_path.replace('.json', '_idmap.json')
    id_map = build_id_map(tree)
    with open(idmap_path, 'w', encoding='utf-8') as f:
        json.dump(id_map, f, ensure_ascii=False, indent=2)
    print(f"ID map saved to: {idmap_path}")

    # Stats
    flat_list = flatten_tree(tree)
    print(f"\nStats:")
    print(f"  Root topics: {len(tree)}")
    print(f"  Total nodes: {len(flat_list)}")
    print(f"  Max depth: {max(n['level'] for n in flat_list)}")


if __name__ == '__main__':
    main()
