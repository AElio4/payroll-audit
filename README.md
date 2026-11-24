# payroll-audit

**I built this because payroll kept missing items on my pay stubs.**

I install garage doors. I'm paid per item: a base rate for each door, plus
openers, rails, framing, tear outs, angle iron, warranty calls, crew rates and
so on. Every week I'd sit
with my invoices and my stub and check them line by line, and most weeks
something was missing. A $10 tear out here, a $35 warranty call there, once a
whole $185 door.

So I automated the check. I take a photo of my invoices and my pay stub, and
this tool:

1. **Reads the photos** with an LLM (Claude) into strict, validated JSON.
2. **Prices every item** with a plain rules engine driven by my pay chart
   (`config/pay_rules.toml`). The AI never decides a dollar amount.
3. **Matches** what I should have been paid against what the stub shows.
4. **Drafts the correction email** in the same format I already send payroll.

I'm also moving into cybersecurity, so I built it the way I'd want any tool
that handles other people's data to be built. A photo of an invoice holds a
customer's name, address and phone number, and the photo file itself can hold
the GPS location of their house. And an LLM that reads images can be talked to
by whatever is written in those images. The [threat model](THREAT_MODEL.md)
covers both.

> Everything in this repo is made up. The two test pay periods are real
> shortfalls I found, re-created with fake names, dates and invoice numbers.
> There are no photos in this repo, and CI fails if one is ever added.

## Example

```
$ python -m payroll_audit audit --jobs tests/fixtures/run2_jobs.json --stub tests/fixtures/run2_stub.json

Pay period 2026-03-09 to 2026-03-15, stub total $1,630.69
Policy: warranty_two_tech=each, tear_out_basis=per_door

MISSING (3 items, $205.00)
  Reyes 03/10  $10.00  wood door tear out $10  [handwritten line 3]
  Marsh 03/12  $185.00  door 18' NWL $185  [printed line 1]
  Lindqvist 03/13  $10.00  wood door tear out $10  [handwritten line 4]

FOR YOU ONLY (never sent to payroll)
  small_extra Ellison 03/14  $2.69  paid row with no matching item (small extra, ignored)

----- DRAFT EMAIL (review before sending) -----

Missing items

Reyes 3/10
wood door tear out $10

Marsh 3/12
door 18' NWL $185

Lindqvist 3/13
wood door tear out $10

Total: $205
```

Every missing item points back to the job and line it came from, and whether
that line was printed or written in by hand. That's what makes the email
easy for payroll to check.

## How it works

```
photos ──► extract.py ──► models.py ──► rules.py ──► audit.py ──► email_draft.py
          (Claude, no     (strict       (pay chart,   (match by     (draft only,
           tools, EXIF     schema,       no AI)        amount per    a human
           stripped)       closed enum)                job)          sends it)
                                                           │
                                                           └──► audit_log.py
                                                                (hash-chained,
                                                                 no names)
```

| File | What it does |
|---|---|
| `config/pay_rules.toml` | My pay chart as data. Change a rate here, not in code. |
| `src/payroll_audit/models.py` | The schema the AI must fill in. No fields for addresses or phone numbers. |
| `src/payroll_audit/extract.py` | Sends cleaned photos to Claude and validates the reply. |
| `src/payroll_audit/rules.py` | Prices each line item and applies crew splits. |
| `src/payroll_audit/audit.py` | Matches expected pay to stub rows by amount. |
| `src/payroll_audit/email_draft.py` | Writes the "Missing items" email. Never includes overpayments. |
| `src/payroll_audit/redact.py` | Scrubs PII from text and pseudonymizes names for logs. |
| `src/payroll_audit/audit_log.py` | Tamper-evident log tying each finding to its source line. |

### Pay rules worth knowing

- Stub rows don't say what they're for, only an amount per job, so matching is
  by amount. Largest items are matched first.
- On a multi-tech job every item is split evenly, including crew rates (a
  2-man half day is $60 per job, so $30 each).
- Handwritten notes count as work done (`+ ORB`, `+21 ft angle`, `Wood`
  written over a printed `steel`). `Warranty - <Name>` written at the top of an
  invoice is its own $35 call.
- Small unexplained extras (like a $2.69 parts bonus) aren't flagged.
- **Overpayments are shown to me but never put in the email.**

### Open questions

Two rules I'm still confirming with payroll are switches, not hard-coded
guesses:

```
--warranty-two-tech each|split   # 2-tech warranty: $35 each, or split?
--tear-out per_door|per_job      # wood tear out: per door, or once per job?
```

A test shows how much each choice changes the result.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # offline, no API key needed

# Offline, from JSON
python -m payroll_audit audit --jobs tests/fixtures/run1_jobs.json --stub tests/fixtures/run1_stub.json

# From photos
cp .env.example .env        # add your ANTHROPIC_API_KEY, then load it into your shell
python -m payroll_audit run --invoices inv1.jpg inv2.jpg --stub stub.jpg --log private/audit.jsonl
python -m payroll_audit verify-log private/audit.jsonl
```

Keep real photos and logs in `private/` (git-ignored) or anywhere outside the
repo.

## Security at a glance

- **Prompt injection:** the model only transcribes. It has no tools, can't
  send anything, and its output must fit a strict schema with a closed list of
  item types. Text in a photo that looks like instructions sets a flag (from
  the model and from a local check), and a flagged run won't draft an email.
- **Data minimization:** the schema can't hold addresses, phones or emails.
  Customers are recorded by last name only.
- **Photo metadata:** photos are re-encoded in memory before upload, which
  drops EXIF data such as GPS. Photos are never written to disk.
- **Integrity checks:** stub rows must add up to the printed total, or no email
  is drafted.
- **Secrets:** API keys come from environment variables only. `.env` is
  git-ignored and CI runs a secret scan.
- **Audit trail:** every finding is logged with its source line and the photo's
  SHA-256, customers are pseudonymized with a keyed hash, and each record
  chains to the previous one so edits are detectable.
- **Human in the loop:** the tool drafts; I send.

Details are in [THREAT_MODEL.md](THREAT_MODEL.md).

## License

MIT
