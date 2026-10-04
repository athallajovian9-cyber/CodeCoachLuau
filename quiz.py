"""Quiz game for CodeCoach Luau: random Roblox coding riddles for kids.
Answering correctly awards stars, badges, and Roblox coder titles.
Scores and unlocked rewards are saved in kid_rewards.json.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAVE_FILE = HERE / "kid_rewards.json"

QUESTIONS = [
    {
        "q": "In Roblox Luau, what keyword creates a local variable?",
        "options": ["A) local", "B) var", "C) let", "D) make"],
        "answer": "A",
        "fact": "Always use 'local' to keep variables clean and fast inside your script!",
    },
    {
        "q": "What special value means 'nothing' or 'empty' in Luau?",
        "options": ["A) null", "B) nil", "C) none", "D) zero"],
        "answer": "B",
        "fact": "In Luau and Lua, empty variables or missing items evaluate to nil!",
    },
    {
        "q": "Which symbol joins two strings together in Luau?",
        "options": ["A) +", "B) &", "C) ..", "D) ->"],
        "answer": "C",
        "fact": "Two dots '..' glue strings together: 'Roblox' .. ' Pro'!",
    },
    {
        "q": "How do you write a comment in Luau?",
        "options": ["A) # comment", "B) -- comment", "C) // comment", "D) /* comment */"],
        "answer": "B",
        "fact": "Two dashes '--' turn the rest of the line into a secret note!",
    },
    {
        "q": "Which method should you use when waiting for a Roblox part to load?",
        "options": [
            "A) FindFirstChild()",
            "B) WaitForChild()",
            "C) search()",
            "D) waitPart()",
        ],
        "answer": "B",
        "fact": "WaitForChild('PartName') pauses safely until the part spawns in game!",
    },
    {
        "q": "What keyword ends an 'if' statement or function in Luau?",
        "options": ["A) end", "B) stop", "C) }", "D) finish"],
        "answer": "A",
        "fact": "In Luau, blocks are always closed with the 'end' keyword!",
    },
    {
        "q": "What built-in function prints messages to the Roblox Output window?",
        "options": ["A) echo()", "B) write()", "C) print()", "D) display()"],
        "answer": "C",
        "fact": "print() sends messages straight to the Roblox Studio Output window!",
    },
]

TITLES = [
    (0, "🧱 Studio Novice"),
    (3, "🕹️ Obby Builder"),
    (7, "🚀 Game Scripter"),
    (12, "👑 Roblox Dev Master"),
    (20, "⭐ Roblox Legend"),
]

BADGES = [
    (1, "⭐ First Star!", "Answered your first Roblox Luau riddle!"),
    (3, "🎮 Scripter Spark!", "3 correct Luau answers!"),
    (5, "🛡️ Bug Blaster!", "5 correct answers! You know your Roblox code!"),
    (10, "🏆 Studio Champion!", "10 correct answers! Studio wizard!"),
]


def load_rewards() -> dict:
    if SAVE_FILE.is_file():
        try:
            return json.loads(SAVE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"stars": 0, "streak": 0, "badges": []}


def save_rewards(data: dict):
    SAVE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_title(stars: int) -> str:
    current = TITLES[0][1]
    for req, title in TITLES:
        if stars >= req:
            current = title
    return current


def play():
    rewards = load_rewards()
    stars = rewards.get("stars", 0)
    badges = set(rewards.get("badges", []))

    print("\n" + "=" * 60)
    print("      🎮 ROBLOX LUAU BRAIN CHALLENGE FOR KIDS! 🎮")
    print(f"      Current Rank: {get_title(stars)}")
    print(f"      Total Stars: {'⭐' * min(stars, 15)} ({stars} stars)")
    print("=" * 60 + "\n")

    item = random.choice(QUESTIONS)
    print(f"  ❓ QUESTION:")
    print(f"  {item['q']}\n")
    for opt in item["options"]:
        print(f"    {opt}")
    print()

    choice = input("  Your answer (A, B, C, or D): ").strip().upper()

    if choice == item["answer"]:
        stars += 1
        rewards["stars"] = stars
        print("\n" + "🎉" * 20)
        print("  CORRECT! You earned +1 Star! ⭐")
        print(f"  Roblox Fact: {item['fact']}")
        print("🎉" * 20)

        new_badges = []
        for req, b_name, b_desc in BADGES:
            if stars >= req and b_name not in badges:
                badges.add(b_name)
                new_badges.append((b_name, b_desc))

        if new_badges:
            print("\n  🎊 NEW REWARD UNLOCKED! 🎊")
            for b_name, b_desc in new_badges:
                print(f"    🏅 {b_name} - {b_desc}")

        rewards["badges"] = sorted(list(badges))
        print(f"\n  Your New Rank: {get_title(stars)}")
    else:
        print("\n  Nice try! Almost had it!")
        print(f"  The right answer was {item['answer']}.")
        print(f"  💡 Roblox Clue: {item['fact']}")

    save_rewards(rewards)
    print("\n" + "-" * 60)
    print(f"  Total Stars: {stars} ⭐ | Badges Unlocked: {len(rewards['badges'])}")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    play()
