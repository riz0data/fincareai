# Design Document: Zero-Touch AI Financial Navigator for Oncology Patients

## 1. Problem Statement

### 1.1 The Cost of Cancer Care Is Rising Fast, and Patients Are Absorbing It

The cost of cancer care in the United States was estimated at $183 billion in 2015, and is projected to exceed $245 billion by 2030. Newly approved cancer drugs now cost an average of $283,000 annually, an increase of 53 percent from $185,620 in 2017. Older adults face cancer-attributable costs as high as approximately $121,700 per year in the last year of life, and approximately $45,100 in the first year after diagnosis alone.

Patients are shouldering a growing share of this directly: cancer patients pay an estimated $16 billion out-of-pocket annually for cancer treatment nationally, and a large study found increased out-of-pocket costs for privately insured patients under 65, driven by rising cost-sharing structures.

### 1.2 Financial Toxicity Is a Documented, Severe Harm, Not a Side Issue

Research has coined the term "financial toxicity" to describe this burden, and the data is stark. Cancer patients are more than twice as likely to declare bankruptcy as those without a cancer diagnosis, with one study finding cancer patients are 2.65 times more likely to file for medical bankruptcy, and between 12 percent and 62 percent reporting they are in debt because of their cancer care. A systematic review found some patients have depleted their life savings within two years of diagnosis, 28 percent have out-of-pocket costs exceeding 20 percent of their annual income, and 2 percent file for medical bankruptcy outright.

Critically, this is not just a financial problem, it is a health and emotional one. Studies have shown that patients who have financial toxicity reported having a lower quality of life, more symptoms, and more pain, and one study showed that some patients felt financial toxicity was more severe than physical, emotional, social, or family distress. More than 30 percent of patients perceived financial distress as being more severe than physical, emotional, social, or family distress. Patients with financial toxicity are also more likely to miss healthcare appointments and have lower medication adherence, meaning the financial burden directly undermines treatment outcomes and survival, not just quality of life.

### 1.3 Small Independent Oncology Practices Lack the Staff to Help

Despite this documented harm, financial navigation support is inconsistent and skewed toward large, well-resourced systems. Survey data shows fewer than 50 percent of community oncology practices routinely provide financial counselors or proactively discuss treatment costs with patients, and where dedicated financial navigators do exist, that coverage is skewed toward larger, hospital-affiliated systems rather than small independent practices.

Using rough market sizing: an estimated 6,000 to 8,000 oncologists work in small, independent (non-hospital-owned) practice settings in the US, serving an estimated 1.8 million to 3.25 million active cancer patients annually. If over half of these practices have no proactive financial navigation function, well over a million cancer patients a year are going through treatment at a small practice with no one proactively connecting them to the assistance programs that exist to help them.

### 1.4 The Result: A Real, Documented, and Solvable Gap

The resources to help these patients already exist: foundations such as CancerCare, the Patient Advocate Foundation, the PAN Foundation, and the Leukemia and Lymphoma Society's Patient Aid Program actively fund copay and treatment-cost assistance. The gap is not the existence of help, it is the absence of a proactive, low-effort bridge connecting overwhelmed patients at understaffed practices to help that already exists.

---

## 2. Current Manual Process (As-Is State)

Today, a cancer patient at a small independent practice navigating financial assistance typically experiences one of the following paths:

- **No proactive support at all.** Most common outcome at small practices, per the survey data above; the patient discovers financial hardship only after bills accumulate, often after skipping appointments or medications.
- **Reactive, patient-initiated outreach.** A patient or family member searches independently, discovers a foundation such as the Patient Advocate Foundation, and self-refers. PAF provides free national case management, but capacity is rationed daily and the process is opt-in and reactive rather than integrated into the care journey.
- **Staffed navigation at larger/affiliated systems.** Where a financial navigator or platform such as TailorMed exists, a human staff member actively works applications on the patient's behalf. This works, but requires practice staff time and budget that small independent practices typically do not have.
- **Manual paperwork burden.** Even when a patient identifies the right program, applications are typically paper or PDF-based, requiring the patient (often mid-treatment, fatigued, and stressed) to gather documentation and complete forms with no help.

The common failure point across all of these paths is the same: nothing proactively closes the gap for a patient at a practice with no financial navigator, and the process depends on the patient having the time, health, and know-how to self-advocate while managing a serious illness.

---

## 3. Proposed Solution: Zero-Touch, AI-Guided Financial Navigation

### 3.1 Design Principles

- **Zero touch for the practice.** A small practice with no financial navigator can still offer this support; there is no staff workflow to operate.
- **Human safety net, always available.** A live human, by phone or video, is available at any point in the journey; the AI never operates without this backstop.
- **Human final review.** Every application is reviewed and acknowledged by a human before submission; the AI assists and prepares, it does not decide or submit unilaterally.
- **Trust before task.** The experience is designed to build trust before asking for sensitive personal and financial information.
- **End-to-end tracking.** Every step, from first contact to funds actually reaching the patient, is timestamped and tracked, producing verifiable proof of impact.

### 3.2 End-to-End Patient Journey

**Step 1: Handoff.** The practice hands the patient a URL or QR code, at diagnosis, during treatment planning, or at any point staff sense financial stress. No scheduling, referral, or staff follow-up required.

**Step 2: Trust-building conversation.** The AI opens with an empathetic, plain-language conversation, explaining what the tool is, that it is connected to real, established assistance foundations, and that a human is available any time the patient wants one. This stage exists specifically to overcome a well-documented trust barrier to AI-guided help in sensitive medical and financial contexts.

**Step 3: Conversational information gathering.** The AI conversationally gathers the details needed to assess eligibility (diagnosis, insurance status, household income and size, treatment costs), using natural language understanding to handle real, unstructured patient responses rather than a rigid form.

**Step 4: Multi-agent collaboration behind the scenes.** A set of specialized agents collaborate to move the case forward: an intake and conversation agent, an eligibility-matching agent that applies deterministic rules against real foundation criteria, a form-preparation agent that populates the correct application, and a risk or escalation agent that flags ambiguous or complex cases for closer human attention.

**Step 5: Human review and sign-off.** A human reviewer checks the prepared application for accuracy and appropriateness, and formally acknowledges it with the patient before anything is submitted. This is the core liability and trust safeguard: the AI prepares, a human decides.

**Step 6: Submission and tracking.** The application is submitted to the relevant foundation. The system timestamps this event and tracks it through to outcome.

**Step 7: Outcome verification.** The system tracks whether the assistance is actually approved, and whether it actually reduces the patient's real bill, closing the loop from first contact to verified financial relief. This creates an independently tracked, patient-level record of impact.

### 3.3 Why Agentic AI, Specifically

The conversational layer (Steps 2 and 3) is where agentic AI is genuinely necessary, not merely convenient: patients describe their situations in messy, unstructured, emotional language, and a rigid form has real dropout risk for an already-overwhelmed patient. The eligibility logic itself (Step 4) remains deterministic and rule-based wherever possible, for auditability and predictability; agentic reasoning is reserved for natural language understanding, conversational repair (asking clarifying follow-ups), and judgment calls on genuinely ambiguous or borderline cases.

---

## 4. Dual Purpose of This Project

This system is designed to serve two goals simultaneously:

1. **A real nonprofit tool** addressing a documented, large-scale gap in cancer financial toxicity support for small oncology practices.
2. **A demonstrated, end-to-end AI architecture portfolio piece**, showcasing agentic system design, human-in-the-loop safety patterns, multi-agent orchestration, data and observability pipeline design, and privacy/governance-by-design, all in one coherent, real-world system.
