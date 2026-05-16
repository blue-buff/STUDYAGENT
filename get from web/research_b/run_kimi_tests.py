#!/usr/bin/env python3
"""Run Kimi CLI on all explanation images and extract answers."""
import subprocess
import json
import os
import sys

BASE = '/Users/song/project/STUDYAGENT/get from web'
RESEARCH_B = os.path.join(BASE, 'research_b')
KIMI = '/Users/song/.local/bin/kimi'

# Load ground truth
paper_data = json.load(open(os.path.join(BASE, 'path6_xkw/paper_6339985_with_answers.json')))

# Build ground truth dict
ground_truth = {}
for q in paper_data['results']:
    qid = q.get('questionId', '')
    at = q.get('answerText', '')
    qt = q.get('questionType', '')
    ei = q.get('explanationImages', [])
    if ei and at:
        ground_truth[qid] = {
            'answer': at,
            'type': qt,
            'expl_url': ei[0],
            'img_path': os.path.join(RESEARCH_B, f'test_images/q_{qid}_ex.jpg')
        }

print(f"Ground truth questions: {len(ground_truth)}")
for qid, info in ground_truth.items():
    print(f"  {qid} | {info['type']} | answer={info['answer'][:80]}")

# Run kimi for each image
results = {}
for qid, info in ground_truth.items():
    img_path = info['img_path']
    if not os.path.exists(img_path) or os.path.getsize(img_path) < 500:
        print(f"\nSKIP {qid}: image missing or too small ({os.path.getsize(img_path) if os.path.exists(img_path) else 0} bytes)")
        continue

    print(f"\n--- Processing {qid} ({info['type']}), ground truth: {info['answer'][:60]} ---")

    prompt = f"Read the image file at {img_path}. This is a math problem explanation image with the answer clearly marked (usually at the bottom or end). Extract ONLY the final answer. For multiple choice questions, output the option letter(s) only (e.g., A, C, ABD). For fill-in-blank questions, output the numeric value or simplest form. Output ONLY the answer, no other text."

    cmd = [
        KIMI, '--print', '--quiet', '--yolo',
        '--work-dir', RESEARCH_B,
        '-p', prompt
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        output = result.stdout.strip()

        # With --quiet mode, first line is the answer
        lines = [l.strip() for l in output.split('\n') if l.strip() and 'To resume this session' not in l]
        extracted = lines[0] if lines else 'NO_OUTPUT'

        # Also check stderr for errors
        if result.stderr.strip():
            print(f"  stderr: {result.stderr[:200]}")

        # Normalize comparison
        gt = info['answer'].strip()
        ex = extracted.strip()

        # For fill-in-blank with XML tags, normalize
        gt_simple = gt.replace('【第1空】', '').strip()
        # Remove HTML/XML tags for comparison
        import re
        gt_clean = re.sub(r'<[^>]+>', '', gt_simple).strip()

        is_match = (ex == gt or ex == gt_simple or ex == gt_clean)

        results[qid] = {
            'extracted': ex,
            'ground_truth': gt,
            'type': info['type'],
            'match': is_match
        }
        print(f"  Extracted: '{ex}'")
        print(f"  Ground truth: '{gt}'")
        print(f"  Match: {is_match}")

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 180s")
        results[qid] = {'extracted': 'TIMEOUT', 'ground_truth': info['answer'], 'type': info['type'], 'match': False}
    except Exception as e:
        print(f"  ERROR: {e}")
        results[qid] = {'extracted': f'ERROR: {e}', 'ground_truth': info['answer'], 'type': info['type'], 'match': False}

# Summary
print("\n" + "="*70)
print("RESULTS SUMMARY")
print("="*70)
correct = sum(1 for r in results.values() if r['match'])
total = len(results)
print(f"Overall accuracy: {correct}/{total} = {correct/total*100:.1f}%" if total > 0 else "No results")

# Detail table
print("\nDetail:")
for qid in sorted(results.keys()):
    r = results[qid]
    status = "CORRECT" if r['match'] else "WRONG"
    print(f"  {qid} | {r['type']:8s} | GT: {r['ground_truth'][:40]:40s} | EX: {r['extracted'][:40]:40s} | {status}")

for qtype in sorted(set(r['type'] for r in results.values())):
    type_results = {qid: r for qid, r in results.items() if r['type'] == qtype}
    type_correct = sum(1 for r in type_results.values() if r['match'])
    print(f"  {qtype}: {type_correct}/{len(type_results)} = {type_correct/len(type_results)*100:.1f}%")

# Save results
out_path = os.path.join(RESEARCH_B, 'kimi_results.json')
with open(out_path, 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nResults saved to {out_path}")
