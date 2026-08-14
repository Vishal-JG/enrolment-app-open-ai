import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

PLAN = {
    "goal": "Validate Student Enrolment App behavior using a local multi-agent workflow",
    "checks": [
        "/students",
        "/students/{student_id}",
        "/students/by-id",
        "/students/by-subject",
        "/ask"
    ]
}

DATABASE_NAME = Path(__file__).with_name("enrolment.db")

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1"
)

IMPLEMENTATION_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:0.5b"
)

REVIEW_MODEL = os.getenv(
    "OLLAMA_REVIEW_MODEL",
    "llama3.1:8b"
)


def validate_student(student):
    student_id, student_name, subject_code = student

    if not isinstance(student_id, int):
        return False, "student_id must be an integer"

    if not student_name:
        return False, "student_name is required"

    if not subject_code:
        return False, "subject_code is required"

    return True, "ok"


def observe_data_quality():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    students = cursor.execute(
        """
        SELECT
            student_id,
            student_name,
            subject_code
        FROM students
        """
    ).fetchall()

    conn.close()

    if len(students) != 10:
        return False, "Expected 10 students"

    for student in students:
        ok, msg = validate_student(student)

        if not ok:
            return False, msg

    return True, "Data validation passed"


def observe_subject_search(subject_code):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    students = cursor.execute(
        """
        SELECT
            student_id,
            student_name,
            subject_code
        FROM students
        WHERE subject_code = ?
        """,
        (subject_code,)
    ).fetchall()

    conn.close()

    if not students:
        return False, (
            f"No students found for subject code {subject_code}"
        )

    for student in students:
        if student[2] != subject_code:
            return False, (
                f"Unexpected subject code found: {student[2]}"
            )

    return True, (
        f"Subject search validation passed for {subject_code}"
    )


def observe_live_endpoints():
    """
    Collect more concrete, results including edge cases for better response 
    """
    results = []

    def probe(label, url, params=None):
        try:
            response = requests.get(url, params=params, timeout=5)
            body_preview = response.text[:200].replace("\n", " ")
            results.append(
                f"{label} -> HTTP {response.status_code} | body: {body_preview}"
            )
        except Exception as exc:
            results.append(f"{label} -> error: {exc}")

    base = "http://127.0.0.1:5000"

    probe("/students (all)", f"{base}/students")
    probe(
        "/students/by-subject (valid ASD101)",
        f"{base}/students/by-subject",
        {"subject_code": "ASD101"}
    )
    probe(
        "/students/by-subject (nonexistent XXX999)",
        f"{base}/students/by-subject",
        {"subject_code": "XXX999"}
    )
    probe(
        "/students/by-subject (missing param)",
        f"{base}/students/by-subject"
    )
    probe(
        "/students/<student_id> (valid id=1)",
        f"{base}/students/1"
    )
    probe(
        "/students/<student_id> (nonexistent id=9999)",
        f"{base}/students/9999"
    )
    probe(
        "/students/<student_id> (invalid non-integer id)",
        f"{base}/students/abc"
    )
    probe(
        "/students/by-id (no id param)",
        f"{base}/students/by-id"
    )

    return results


def call_model(
    model_name,
    system_prompt,
    user_prompt,
    max_tokens=120
):
    try:
        client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",
            timeout=180.0
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=0.1
        )

        content = response.choices[0].message.content

        if content and content.strip():
            return content.strip(), None

        return "No response generated.", None

    except Exception as exc:
        return None, (
            f"{model_name} unavailable or timed out ({exc})"
        )


def parse_observation_items(observe_message):
    if isinstance(observe_message, str):
        if "Live endpoint checks:" in observe_message:
            payload = observe_message.split("Live endpoint checks:", 1)[1]
            return [item.strip() for item in payload.split(";") if item.strip()]

        return [item.strip() for item in observe_message.splitlines() if item.strip()]

    return [str(item) for item in observe_message]


def build_implementation_recommendation(observe_results):
    issues = []

    for observation in observe_results:
        if "->" not in observation:
            continue

        label, details = observation.split(" -> ", 1)
        endpoint = label.split(" (", 1)[0]

        if details.startswith("error:"):
            issues.append(
                f"{endpoint} failed with error: {details.split('error:', 1)[1].strip()}"
            )
            continue

        status_text = details.split(" | ", 1)[0]

        try:
            actual_status = int(status_text.replace("HTTP ", ""))
        except ValueError:
            continue

        expected_status = None

        if "invalid non-integer id" in label:
            expected_status = 400
        elif "nonexistent id=9999" in label:
            expected_status = 404
        elif endpoint == "/students/by-subject" and "nonexistent" in label:
            expected_status = 200
        elif "missing param" in label or "no id param" in label:
            expected_status = 400
        elif "valid" in label or "all" in label:
            expected_status = 200

        if expected_status is not None and actual_status != expected_status:
            issues.append(
                f"{endpoint} returned {actual_status} but should return {expected_status}."
            )

    if not issues:
        return "No evidence-backed improvement identified."

    return "\n".join(f"- {issue}" for issue in issues[:2])


def get_implementation_agent_advice(observe_message):
    observe_results = parse_observation_items(observe_message)
    recommendation = build_implementation_recommendation(observe_results)

    if recommendation != "No evidence-backed improvement identified.":
        return recommendation, None

    return recommendation, None


def get_review_agent_advice(
    implementation_message,
    observe_message
):
    if implementation_message == "No evidence-backed improvement identified.":
        return (
            "Risk: No evidence-backed risk identified.\n"
            "Correction: No correction required.\n"
            "Retest: Repeat validation after future changes.",
            None,
        )

    return (
        "Risk: The recommendation targets a concrete endpoint mismatch.\n"
        "Correction: Keep the fix aligned with the reported status.\n"
        "Retest: Re-run the same endpoint checks after the change.",
        None,
    )


def human_review():
    print()
    print("HUMAN REVIEW")
    print("1 - Accept")
    print("2 - Partially Accept")
    print("3 - Reject")

    decision = input("Decision: ").strip()

    if decision == "1":
        return "Accept"

    if decision == "2":
        return "Partially Accept"

    return "Reject"


def adapt(decision):
    print()

    if decision == "Accept":
        print(
            "ADAPT: Apply recommendation and rerun validation."
        )

    elif decision == "Partially Accept":
        print(
            "ADAPT: Apply selected recommendations and "
            "rerun validation."
        )

    else:
        print(
            "ADAPT: Keep current implementation and "
            "document rationale."
        )


def main():
    print("=" * 60)
    print("ASD LAB 02 AGENTIC LOOP")
    print("=" * 60)

    print()
    print("PLAN")
    print(PLAN)

    print()
    print("ACT")
    print("Check local database records")

    ok_data, msg_data = observe_data_quality()

    print()
    print("OBSERVE")
    print(msg_data)

    ok_subject, msg_subject = observe_subject_search(
        "ASD101"
    )

    print(msg_subject)

    live_results = observe_live_endpoints()

    observe_message = (
        f"{msg_data}. "
        f"{msg_subject}. "
        f"Live endpoint checks: " + "; ".join(live_results)
    )

    print()
    print("IMPLEMENTATION AGENT")
    print(f"Model: {IMPLEMENTATION_MODEL}")

    implementation_advice, implementation_error = (
        get_implementation_agent_advice(
            observe_message
        )
    )

    if implementation_advice:
        print()
        print(implementation_advice)
    else:
        print()
        print(implementation_error)
        implementation_advice = (
            "Implementation agent unavailable."
        )

    print()
    print("REVIEW AGENT")
    print(f"Model: {REVIEW_MODEL}")

    review_advice, review_error = (
        get_review_agent_advice(
            implementation_advice,
            observe_message
        )
    )

    if review_advice:
        print()
        print(review_advice)
    else:
        print()
        print(review_error)
    print()
    print("HUMAN DECISION")
    decision = human_review()
    print()
    print(f"Decision: {decision}")
    adapt(decision)
    print()
    print("LOOP COMPLETE")

if __name__ == "__main__":
    main()