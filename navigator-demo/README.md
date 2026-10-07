# Oncology Financial Navigator -- Local Demo

This is a small, self-contained demo of the core logic behind the Oncology
Financial Navigator proof of concept: a patient intake conversation, structured
data extraction, and deterministic eligibility matching against sample
assistance foundations.

## What this demo shows

1. A simulated patient conversation (Intake Agent) -- the questions a real
   patient would be asked, with pre-written sample answers standing in for a
   live conversation.
2. Field extraction -- turning messy natural-language answers into clean
   structured data (household size, income, insurance status, etc).
3. Deterministic, auditable eligibility matching -- real rules-engine code,
   no AI involved in the actual match/no-match decision, checked against three
   sample foundations.

## What's faked for tonight, and why

The field extraction step normally calls a real language model. For this demo,
a small fake function stands in for that model call so you can run this
instantly on your laptop with no API key or internet connection required. The
rules engine, data structures, and conversation flow are all the real project
code, unchanged.

## How to run it

1. Make sure Python 3 is installed. In a terminal, run:
   python3 --version
   You should see something like "Python 3.x.x". If not, install Python 3
   from python.org first.

2. Unzip this folder if you haven't already, and open it in VS Code
   (File > Open Folder...).

3. Open a terminal inside VS Code (Terminal > New Terminal).

4. Run the demo:
   python3 run_demo.py

You should see the simulated conversation print out, followed by the
extracted structured data, followed by a match/no-match result for each
sample foundation.

## Folder structure

- run_demo.py -- the demo script you run.
- app/agents/intake_agent.py -- the real Intake Agent code.
- app/agents/llm_field_extraction.py -- the real LLM-based field extraction
  module (the fake model function used tonight is only inside run_demo.py,
  this module itself is unmodified production code).
- app/rules_engine/eligibility_rules.py -- the real, deterministic eligibility
  rules engine.
- app/data/entities.py -- shared data structures.

## If you want to go further before the conference

- You can change the sample answers in run_demo.py (SAMPLE_ANSWERS list) to
  try a different patient scenario.
- You can add or edit sample foundations in run_demo.py (SAMPLE_FOUNDATIONS
  list) to show different eligibility criteria.
- Wiring in a real model (e.g. Anthropic's API) instead of the fake function
  is possible but requires an API key -- see the commented-out example at the
  bottom of app/agents/llm_field_extraction.py.
