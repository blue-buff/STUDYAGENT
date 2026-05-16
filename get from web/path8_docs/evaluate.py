"""
Evaluate question splitting accuracy through manual review.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field


@dataclass
class QuestionEval:
    question_number: int
    boundary_correct: bool = False      # Start/end boundaries correct?
    type_correct: bool = False           # question_type correct?
    content_complete: bool = False       # question_text complete (no truncation)?
    answer_correct: bool = False         # answer extracted correctly?
    knowledge_points_ok: bool = False    # knowledge_points reasonable?
    notes: str = ""


@dataclass
class EvalReport:
    total_questions: int = 0
    evaluations: list[QuestionEval] = field(default_factory=list)

    @property
    def boundary_accuracy(self) -> float:
        if not self.evaluations:
            return 0.0
        correct = sum(1 for e in self.evaluations if e.boundary_correct)
        return correct / len(self.evaluations)

    @property
    def type_accuracy(self) -> float:
        if not self.evaluations:
            return 0.0
        correct = sum(1 for e in self.evaluations if e.type_correct)
        return correct / len(self.evaluations)

    @property
    def content_accuracy(self) -> float:
        if not self.evaluations:
            return 0.0
        correct = sum(1 for e in self.evaluations if e.content_complete)
        return correct / len(self.evaluations)

    @property
    def answer_accuracy(self) -> float:
        if not self.evaluations:
            return 0.0
        correct = sum(1 for e in self.evaluations if e.answer_correct)
        return correct / len(self.evaluations)

    @property
    def kp_accuracy(self) -> float:
        if not self.evaluations:
            return 0.0
        correct = sum(1 for e in self.evaluations if e.knowledge_points_ok)
        return correct / len(self.evaluations)

    @property
    def overall_accuracy(self) -> float:
        """Average of all five accuracy metrics."""
        return (
            self.boundary_accuracy
            + self.type_accuracy
            + self.content_accuracy
            + self.answer_accuracy
            + self.kp_accuracy
        ) / 5.0

    def to_dict(self) -> dict:
        return {
            "total_questions": self.total_questions,
            "evaluated_questions": len(self.evaluations),
            "boundary_accuracy": round(self.boundary_accuracy, 3),
            "type_accuracy": round(self.type_accuracy, 3),
            "content_accuracy": round(self.content_accuracy, 3),
            "answer_accuracy": round(self.answer_accuracy, 3),
            "knowledge_point_accuracy": round(self.kp_accuracy, 3),
            "overall_accuracy": round(self.overall_accuracy, 3),
            "details": [
                {
                    "question_number": e.question_number,
                    "boundary_correct": e.boundary_correct,
                    "type_correct": e.type_correct,
                    "content_complete": e.content_complete,
                    "answer_correct": e.answer_correct,
                    "knowledge_points_ok": e.knowledge_points_ok,
                    "notes": e.notes,
                }
                for e in self.evaluations
            ],
        }


def print_question_for_review(question: dict, idx: int):
    """Print a question for manual review."""
    print(f"\n{'─'*60}")
    print(f"Question #{idx+1}")
    print(f"  Type:       {question.get('question_type', '?')}")
    print(f"  Difficulty: {question.get('difficulty', '?')}")
    print(f"  Knowledge:  {', '.join(question.get('knowledge_points', []))}")
    print(f"  Confidence: {question.get('extraction_confidence', '?')}")
    print(f"\n  --- Question Text ---")
    qtext = question.get("question_text", "")
    print(f"  {qtext[:500]}")
    if len(qtext) > 500:
        print(f"  ... ({len(qtext)} total chars)")
    print(f"\n  --- Options ---")
    opts = question.get("question_options", [])
    if opts:
        for o in opts:
            print(f"  {o}")
    else:
        print(f"  (none)")
    print(f"\n  --- Answer ---")
    print(f"  {question.get('answer_text', '(none)')}")
    print(f"\n  --- Analysis ---")
    analysis = question.get("analysis", "")
    print(f"  {analysis[:300] if analysis else '(none)'}")
    print(f"\n  --- Notes ---")
    print(f"  {question.get('extraction_notes', '(none)')}")


def interactive_review(questions: list[dict], max_questions: int = 20) -> EvalReport:
    """Interactive manual review of questions."""
    questions = questions[:max_questions]
    report = EvalReport(total_questions=len(questions))

    print(f"\n{'='*60}")
    print(f"Manual Question Review - {len(questions)} questions")
    print(f"Review each question and answer y/n for each criterion")
    print(f"Type 'q' to quit early, 's' to skip a question")
    print(f"{'='*60}")

    for i, q in enumerate(questions):
        print_question_for_review(q, i)

        eval_item = QuestionEval(question_number=i + 1)

        print(f"\n  [Review] Evaluate this question:")
        try:
            boundary = input("    Boundary correct? (y/n/s/q): ").strip().lower()
            if boundary == "q":
                break
            elif boundary == "s":
                continue
            eval_item.boundary_correct = boundary == "y"

            type_ok = input("    Type correct? (y/n/s/q): ").strip().lower()
            if type_ok == "q":
                break
            elif type_ok == "s":
                continue
            eval_item.type_correct = type_ok == "y"

            content = input("    Content complete? (y/n/s/q): ").strip().lower()
            if content == "q":
                break
            elif content == "s":
                continue
            eval_item.content_complete = content == "y"

            answer = input("    Answer correct? (y/n/s/q): ").strip().lower()
            if answer == "q":
                break
            elif answer == "s":
                continue
            eval_item.answer_correct = answer == "y"

            kp = input("    Knowledge points OK? (y/n/s/q): ").strip().lower()
            if kp == "q":
                break
            elif kp == "s":
                continue
            eval_item.knowledge_points_ok = kp == "y"

            notes = input("    Notes (optional): ").strip()
            eval_item.notes = notes

        except EOFError:
            print("\n  [INFO] Interactive mode not available, switching to auto mode")
            break

        report.evaluations.append(eval_item)

    return report


def auto_review(questions: list[dict], max_questions: int = 20) -> EvalReport:
    """Automated review based on heuristics (preview only, not a replacement for manual)."""
    questions = questions[:max_questions]
    report = EvalReport(total_questions=len(questions))

    for i, q in enumerate(questions):
        print_question_for_review(q, i)
        print()

    print(f"\n[INFO] Auto-review mode: all {len(questions)} questions printed above.")
    print("Please review manually and fill in the evaluation template.")
    return report


def evaluate(json_file: str, interactive: bool = False, max_questions: int = 20) -> EvalReport:
    """
    Load pipeline output and evaluate question splitting accuracy.

    Args:
        json_file: Path to pipeline output JSON
        interactive: If True, prompt for manual review of each question
        max_questions: Max questions to review (default 20)
    """
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    if not questions:
        print("No questions found in the output file.")
        return EvalReport(total_questions=0)

    print(f"\nLoaded {len(questions)} questions from {json_file}")
    print(f"Subject: {data.get('subject', '?')}")
    print(f"Knowledge Point: {data.get('knowledge_point', '?')}")

    if interactive:
        report = interactive_review(questions, max_questions)
    else:
        report = auto_review(questions, max_questions)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Evaluation Summary")
    print(f"{'='*60}")
    print(f"  Questions evaluated: {len(report.evaluations)} / {report.total_questions}")
    print(f"  Boundary accuracy:   {report.boundary_accuracy:.1%}")
    print(f"  Type accuracy:       {report.type_accuracy:.1%}")
    print(f"  Content accuracy:    {report.content_accuracy:.1%}")
    print(f"  Answer accuracy:     {report.answer_accuracy:.1%}")
    print(f"  Knowledge Point OK:  {report.kp_accuracy:.1%}")
    print(f"  ────────────────────────")
    print(f"  Overall accuracy:    {report.overall_accuracy:.1%}")

    # Save evaluation report
    report_path = json_file.replace(".json", "_eval.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved to: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate question splitting accuracy",
    )
    parser.add_argument(
        "input_file",
        help="Path to pipeline output JSON file",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive manual review mode",
    )
    parser.add_argument(
        "--max-questions", "-n",
        type=int,
        default=20,
        help="Max questions to review (default: 20)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print the summary from a previous evaluation",
    )

    args = parser.parse_args()

    if args.summary_only:
        with open(args.input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    evaluate(
        json_file=args.input_file,
        interactive=args.interactive,
        max_questions=args.max_questions,
    )


if __name__ == "__main__":
    main()
