#!/usr/bin/env python3
"""Parse the JYE_BOOK_TREE_HOLDER from subject search pages and extract chapter trees."""
import json, sys, re
from pathlib import Path
from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from jyeoo.utils import ensure_dir

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "knowledge_trees"

def parse_tree_holder(holder):
    """Parse <ul id='JYE_BOOK_TREE_HOLDER'> into structured data."""
    editions = []
    for li in holder.find_all('li', recursive=False):
        ek = li.get('ek', '')
        nm = li.get('nm', '')
        edition = {'ek': ek, 'name': nm, 'grades': []}
        inner_ul = li.find('ul')
        if inner_ul:
            for grade_li in inner_ul.find_all('li', recursive=False):
                gd = grade_li.get('gd', '')
                grade_nm = grade_li.get('nm', '')
                bk = grade_li.get('bk', '')
                edition['grades'].append({
                    'bk': bk,
                    'gd': gd,
                    'name': grade_nm,
                })
        editions.append(edition)
    return editions

def main():
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    })

    subjects_to_check = {
        'math': '初中数学',
        'math2': '高中数学',
        'math3': '小学数学',
        'physics': '初中物理',
        'physics2': '高中物理',
        'chemistry': '初中化学',
        'chemistry2': '高中化学',
    }

    all_trees = {}

    for path, name in subjects_to_check.items():
        url = f'https://www.jyeoo.com/{path}/ques/search'
        resp = sess.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')
        holder = soup.find('ul', id='JYE_BOOK_TREE_HOLDER')

        if holder:
            tree = parse_tree_holder(holder)
            all_trees[path] = {'name': name, 'editions': tree}
            print(f"\n{'='*60}")
            print(f"{name} (/{path}/)")
            print(f"{'='*60}")
            for edition in tree:
                print(f"  版本: {edition['name']} (ek={edition['ek']})")
                for grade in edition['grades']:
                    print(f"    {grade['name']} (gd={grade['gd']}, bk={grade['bk'][:24]}...)")
        else:
            print(f"{name}: No tree holder found")
            # Try to find any tree data
            tree_div = soup.find('div', id='divTree')
            if tree_div:
                print(f"  divTree found but empty or different format")

    ensure_dir(OUTPUT_DIR)
    output_path = OUTPUT_DIR / 'chapter_trees.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_trees, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_trees)} subject trees to {output_path}")

    # Stats
    total_editions = sum(len(t['editions']) for t in all_trees.values())
    total_grades = sum(sum(len(e['grades']) for e in t['editions']) for t in all_trees.values())
    print(f"Total editions: {total_editions}")
    print(f"Total grade/book entries: {total_grades}")

if __name__ == '__main__':
    main()
