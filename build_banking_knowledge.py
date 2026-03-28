"""
One-shot generator for banking_knowledge.json — large multimodal training corpus.
Run: python build_banking_knowledge.py
"""
from __future__ import annotations

import hashlib
import json
import os

SEED = {
    "meta": {
        "version": "3.0.0",
        "org": "Intellifox Synthetic Banking Engineering",
        "purpose": "Ground truth + multimodal generation specs (image / video storyboard / TTS / text curriculum)",
        "visual_brand": "Dark navy canvas, electric cyan and indigo accents, glass morphism cards, thin monospace labels, no cartoon humans in diagrams",
        "audio_brand": "Warm authoritative narrator, 0.92 playback clarity, slight room tone, avoid robotic pacing",
    },
    "systems": [
        {
            "id": "core-banking",
            "name": "Core Banking System",
            "description": "Heart of all financial operations — accounts, ledger, transactions, reconciliation. Handles 2M+ transactions/day.",
            "tech_stack": ["Java 17", "Spring Boot", "Oracle DB", "Kafka", "Redis"],
            "owning_team": "Platform Engineering",
            "owner": "Vikram Nair",
            "apis": ["/accounts/{id}/balance", "/accounts/{id}/transfer", "/ledger/reconcile", "/auth/token"],
            "dependencies": ["fraud-detection", "notification-service", "audit-service"],
            "risk_level": "critical",
            "sla": "99.99%",
            "known_issues": ["PR #847: OAuth→PKCE migration (breaking change)", "Nightly batch deadlock fixed in PR #809"],
        },
        {
            "id": "mobile-banking",
            "name": "Mobile Banking App",
            "description": "Customer-facing React Native app serving 4M+ users on iOS and Android. Real-time balance, UPI, bill pay.",
            "tech_stack": ["React Native", "TypeScript", "Redux", "Firebase"],
            "owning_team": "Digital Products",
            "owner": "Amit Trivedi",
            "apis": ["/api/dashboard", "/api/pay/upi", "/api/bills", "/api/statements"],
            "dependencies": ["core-banking", "api-gateway", "notification-service", "kyc-service"],
            "risk_level": "high",
            "sla": "99.95%",
            "known_issues": ["Session timeout edge case on biometric re-auth"],
        },
        {
            "id": "payment-gateway",
            "name": "Payment Gateway",
            "description": "Processes all inbound/outbound payments: NEFT, RTGS, IMPS, UPI, international wires. 50K TPS capacity.",
            "tech_stack": ["Go", "gRPC", "PostgreSQL", "Kafka", "Envoy"],
            "owning_team": "Payments Team",
            "owner": "Sneha Verma",
            "apis": ["/payment/initiate", "/payment/status/{txnId}", "/payment/webhook"],
            "dependencies": ["core-banking", "fraud-detection", "rbi-clearing-api"],
            "risk_level": "critical",
            "sla": "99.999%",
            "known_issues": ["International wire SWIFT timeout above 30s needs retry logic"],
        },
        {
            "id": "fraud-detection",
            "name": "Fraud Detection Engine",
            "description": "ML-based real-time fraud scoring. Evaluates every transaction in <50ms using behavioral + rule-based models.",
            "tech_stack": ["Python", "FastAPI", "XGBoost", "TensorFlow", "Redis", "Flink"],
            "owning_team": "Risk & Security",
            "owner": "Priya Singh",
            "apis": ["/score/transaction", "/score/login", "/rules/update"],
            "dependencies": ["core-banking", "kyc-service", "audit-service"],
            "risk_level": "critical",
            "sla": "99.98%",
            "known_issues": ["Model drift alerts if >2 weeks without retraining"],
        },
        {
            "id": "kyc-service",
            "name": "KYC / AML Service",
            "description": "Know Your Customer & Anti-Money Laundering compliance. Integrates with CKYC registry, UIDAI, Experian.",
            "tech_stack": ["Python", "FastAPI", "MongoDB", "Celery", "RabbitMQ"],
            "owning_team": "Compliance Engineering",
            "owner": "Rahul Kumar",
            "apis": ["/kyc/verify", "/aml/screen", "/kyc/status/{customerId}"],
            "dependencies": ["core-banking", "document-service", "external-ckyc-api"],
            "risk_level": "high",
            "sla": "99.9%",
            "known_issues": ["UIDAI API rate limits at 10K requests/min — throttling in place"],
        },
        {
            "id": "api-gateway",
            "name": "API Gateway",
            "description": "Central entry point for all external traffic. Handles auth, rate limiting, routing, observability.",
            "tech_stack": ["Kong", "Nginx", "Lua", "Prometheus", "Grafana"],
            "owning_team": "Platform Engineering",
            "owner": "Vikram Nair",
            "apis": ["/gateway/health", "/gateway/routes", "/gateway/metrics"],
            "dependencies": ["core-banking", "mobile-banking", "loan-origination"],
            "risk_level": "critical",
            "sla": "99.999%",
            "known_issues": ["Rate limit config pushed via PR #831 — 100 req/min per client"],
        },
        {
            "id": "loan-origination",
            "name": "Loan Origination System",
            "description": "End-to-end loan processing — application, underwriting, credit scoring, disbursement. Handles 5K applications/day.",
            "tech_stack": ["Node.js", "Express", "PostgreSQL", "Kafka", "Temporal"],
            "owning_team": "Lending Team",
            "owner": "Deepa Sharma",
            "apis": ["/loan/apply", "/loan/status/{id}", "/loan/disburse", "/loan/emi-schedule"],
            "dependencies": ["core-banking", "kyc-service", "credit-bureau-api", "notification-service"],
            "risk_level": "high",
            "sla": "99.9%",
            "known_issues": ["PR #201: Race condition in disbursement saga — double disbursement risk patched"],
        },
        {
            "id": "notification-service",
            "name": "Notification Service",
            "description": "Omnichannel notification platform — SMS, Push, Email, WhatsApp. 10M+ messages/day.",
            "tech_stack": ["Node.js", "Bull Queue", "Redis", "Twilio", "Firebase FCM", "SendGrid"],
            "owning_team": "Digital Products",
            "owner": "Amit Trivedi",
            "apis": ["/notify/send", "/notify/template/{id}", "/notify/status/{msgId}"],
            "dependencies": ["core-banking", "external-sms-provider", "email-provider"],
            "risk_level": "medium",
            "sla": "99.9%",
            "known_issues": ["WhatsApp Business API quota limits during month-end statements"],
        },
        {
            "id": "card-management",
            "name": "Card Management System",
            "description": "Issues and manages credit/debit cards — Visa, Mastercard, RuPay. Controls limits, blocks, EMI conversion.",
            "tech_stack": ["Java", "Spring Boot", "Oracle DB", "HSM Integration"],
            "owning_team": "Cards Team",
            "owner": "Suresh Iyer",
            "apis": ["/card/issue", "/card/block", "/card/limit", "/card/emi-convert"],
            "dependencies": ["core-banking", "fraud-detection", "notification-service", "visa-network-api"],
            "risk_level": "high",
            "sla": "99.95%",
            "known_issues": ["HSM failover takes ~90s — known latency spike on key rotation"],
        },
        {
            "id": "treasury-management",
            "name": "Treasury Management System",
            "description": "Manages bank liquidity, ALM, forex positions, investment portfolio. Used by treasury desk daily.",
            "tech_stack": ["Python", "FastAPI", "TimescaleDB", "Bloomberg API", "Pandas"],
            "owning_team": "Finance Technology",
            "owner": "Anita Rao",
            "apis": ["/treasury/positions", "/treasury/alm-report", "/treasury/forex-rate"],
            "dependencies": ["core-banking", "bloomberg-api", "rbi-data-api"],
            "risk_level": "high",
            "sla": "99.9%",
            "known_issues": ["Bloomberg API disconnect at market close needs auto-reconnect"],
        },
        {
            "id": "analytics-platform",
            "name": "Data Analytics Platform",
            "description": "Real-time and batch analytics. Powers dashboards, regulatory reports, customer 360, risk metrics.",
            "tech_stack": ["Apache Spark", "Databricks", "dbt", "BigQuery", "Tableau", "Airflow"],
            "owning_team": "Data Engineering",
            "owner": "Kiran Joshi",
            "apis": ["/analytics/query", "/analytics/report/{reportId}", "/analytics/dashboard"],
            "dependencies": ["core-banking", "loan-origination", "card-management", "treasury-management"],
            "risk_level": "medium",
            "sla": "99.5%",
            "known_issues": ["BigQuery slot contention during month-end — scale-up needed"],
        },
        {
            "id": "digital-onboarding",
            "name": "Digital Onboarding",
            "description": "Paperless account opening — video KYC, document upload, e-sign, instant account activation.",
            "tech_stack": ["React", "Node.js", "AWS S3", "WebRTC", "DocuSign API"],
            "owning_team": "Digital Products",
            "owner": "Amit Trivedi",
            "apis": ["/onboard/start", "/onboard/vkyc", "/onboard/esign", "/onboard/status"],
            "dependencies": ["kyc-service", "core-banking", "notification-service", "document-service"],
            "risk_level": "medium",
            "sla": "99.9%",
            "known_issues": ["Video KYC drops on 2G networks — adaptive bitrate needed"],
        },
    ],
    "teams": [
        {"name": "Platform Engineering", "responsibilities": ["Core infrastructure", "API Gateway", "DevOps", "Security"], "owned_systems": ["core-banking", "api-gateway"], "head": "Vikram Nair", "size": 45},
        {"name": "Digital Products", "responsibilities": ["Mobile app", "Web portal", "Notifications", "Digital onboarding"], "owned_systems": ["mobile-banking", "notification-service", "digital-onboarding"], "head": "Amit Trivedi", "size": 60},
        {"name": "Risk & Security", "responsibilities": ["Fraud detection", "Cybersecurity", "Risk models", "Penetration testing"], "owned_systems": ["fraud-detection"], "head": "Priya Singh", "size": 25},
        {"name": "Payments Team", "responsibilities": ["Payment rails", "SWIFT/SEPA", "UPI ecosystem", "Settlement"], "owned_systems": ["payment-gateway"], "head": "Sneha Verma", "size": 30},
        {"name": "Lending Team", "responsibilities": ["Loan products", "Underwriting automation", "Collections", "Credit risk"], "owned_systems": ["loan-origination"], "head": "Deepa Sharma", "size": 35},
    ],
    "processes": {
        "deployment": {
            "steps": ["Feature branch", "PR with 2 approvals", "Staging CI/CD (20 min)", "Smoke tests (30 min)", "Blue-green prod deploy", "Canary 5% → 100%"],
            "tools": ["GitHub Actions", "ArgoCD", "Helm", "Datadog"],
        },
        "incident": {
            "steps": ["PagerDuty alert", "On-call ack (15 min SLA)", "#incidents Slack war room", "RCA doc in 24h", "Postmortem in 72h"],
            "severity": {"P0": "CEO notified, war room", "P1": "VP notified, 1h fix", "P2": "Manager notified, 4h fix", "P3": "Normal sprint"},
        },
        "onboarding": {
            "week1": "Access setup, architecture overview, shadow senior dev",
            "week2": "First PR with mentor review, local dev environment",
            "week3": "Pair programming, on-call shadowing",
            "week4": "First solo feature, code review, team retro",
        },
    },
}

DOMAINS = [
    "Trade Finance & LC",
    "Custody & Securities",
    "Open Banking / PSD2",
    "Blockchain Settlement Pilot",
    "Wealth Advisory Engine",
    "Insurance Bancassurance",
    "Regulatory Reporting (Basel)",
    "Credit Bureau Mesh",
    "Merchant Acquiring",
    "ATM Switch & Cash",
    "Corporate Internet Banking",
    "Retail CRM & Leads",
    "Document Intelligence OCR",
    "HSM & Key Ceremony",
    "SIEM & SOAR",
    "Data Lakehouse Ingest",
    "Feature Store / MLOps",
    "Customer Data Platform",
    "Pricing & Offers",
    "Collections & Recovery",
    "Limits & Collateral",
    "Swift gpi Tracker",
    "FX Options Desk",
    "Islamic Banking Core",
    "Green Finance ESG",
]

RISK_ROT = ["critical", "high", "high", "medium", "medium", "low"]
TECH_BAG = [
    ["Rust", "Axum", "ScyllaDB", "NATS"],
    ["Kotlin", "Spring", "PostgreSQL", "Debezium"],
    ["C#", ".NET 8", "SQL Server", "Service Bus"],
    ["Scala", "Akka", "Cassandra", "Pulsar"],
    ["Elixir", "Phoenix", "ETS", "RabbitMQ"],
    ["Python", "Django", "MySQL", "Celery"],
    ["Java", "Quarkus", "Oracle", "Kafka"],
    ["Go", "Fiber", "TiDB", "gRPC"],
    ["TypeScript", "NestJS", "MongoDB", "Redis"],
    ["Ruby", "Rails", "Postgres", "Sidekiq"],
]


def gen_extra_systems(count: int) -> list:
    out = []
    seed_ids = {s["id"] for s in SEED["systems"]}
    for i in range(count):
        dom = DOMAINS[i % len(DOMAINS)]
        sid = f"synth-{dom.lower().replace(' ', '-').replace('/', '-')}-{i // len(DOMAINS) + 1}"
        sid = "".join(c if c.isalnum() or c == "-" else "-" for c in sid)
        while sid in seed_ids:
            sid = sid + "-x"
        seed_ids.add(sid)
        tech = TECH_BAG[i % len(TECH_BAG)]
        risk = RISK_ROT[i % len(RISK_ROT)]
        deps_pool = [s["id"] for s in SEED["systems"]][:6]
        d1, d2 = deps_pool[i % len(deps_pool)], deps_pool[(i + 2) % len(deps_pool)]
        out.append(
            {
                "id": sid,
                "name": f"{dom} Platform ({i + 1})",
                "description": (
                    f"Regional orchestration layer for {dom}: multi-tenant APIs, policy enforcement, "
                    f"observability SLOs, and cross-border data residency controls. Synthetic workload tier {i % 7 + 1}."
                ),
                "tech_stack": tech + ["OpenTelemetry", "Vault"],
                "owning_team": SEED["teams"][i % len(SEED["teams"])]["name"],
                "owner": f"Owner Pool {i % 40 + 1}",
                "apis": [
                    f"/{sid[:8]}/v1/health",
                    f"/{sid[:8]}/v1/batch",
                    f"/{sid[:8]}/v1/stream",
                    f"/{sid[:8]}/v1/policy/eval",
                ],
                "dependencies": list({d1, d2}),
                "risk_level": risk,
                "sla": f"99.{90 + (i % 9)}%",
                "known_issues": [
                    f"Chaos test {i}: partition healing > {(i % 5) + 2}s under peak",
                    f"DR drill backlog item DR-{4000 + i}",
                ],
                "multimedia_training": {
                    "diagram_layers": [
                        "Edge API mesh → regional gateway → policy PDP → domain microservices → event bus → analytical sink",
                        "Secrets: HSM-backed signing, short-lived SPIFFE identities, mTLS everywhere",
                        f"Data classification: {dom} PII flows tagged with lineage IDs",
                    ],
                    "video_storyboard_beats": [
                        {
                            "t": "0:00-0:12",
                            "visual_prompt": f"Cinematic isometric {dom} control room, LED wall with live latency heatmap, no faces",
                            "voiceover": f"In {dom}, every request crosses policy, identity, and evidence boundaries before touching core ledgers.",
                            "lower_third": f"Module · {dom}",
                            "b_roll": ["packet flow animation", "lock icon morphing to key"],
                        },
                        {
                            "t": "0:12-0:28",
                            "visual_prompt": f"Abstract network graph pulsing on dark glass; highlight path through {tech[0]} services",
                            "voiceover": "We trace golden signals—latency, errors, saturation—then tie them to customer journeys and regulatory evidence packs.",
                            "lower_third": "Observability spine",
                            "b_roll": ["Grafana-style charts stylized", "trace waterfall"],
                        },
                        {
                            "t": "0:28-0:45",
                            "visual_prompt": "Split screen: incident timeline + code diff + rollback canary slider",
                            "voiceover": "When risk spikes, runbooks converge: freeze feature flags, widen canary, engage domain on-call, preserve audit trail.",
                            "lower_third": "Resilience playbook",
                            "b_roll": ["pager animation", "checklist ticks"],
                        },
                    ],
                    "image_generation_presets": [
                        {
                            "preset_id": f"{sid}-arch-01",
                            "use_case": "executive_architecture_slide",
                            "positive_prompt": (
                                f"Enterprise architecture diagram: {dom}, dark background, cyan edges, labeled boxes for API, policy, data plane, "
                                f"analytics; arrows for sync and async; legend for risk tier"
                            ),
                            "negative_prompt": "cluttered, comic, handwritten, low contrast, watermark",
                            "aspect_ratio": "16:9",
                        },
                        {
                            "preset_id": f"{sid}-ops-02",
                            "use_case": "sre_oncall_wallboard",
                            "positive_prompt": (
                                f"NOC style wallboard for {dom}: SLO burn, error budget, active incidents, synthetic probes world map"
                            ),
                            "negative_prompt": "people faces, stock photo office",
                            "aspect_ratio": "21:9",
                        },
                    ],
                    "tts_chapters": [
                        {
                            "chapter": "cold_open",
                            "script": f"Welcome to the deep dive on {dom}. Picture millions of events per hour, each one accountable.",
                            "pace_wpm": 148,
                            "emotion": "confident_warm",
                        },
                        {
                            "chapter": "deep_dive",
                            "script": (
                                f"We will map dependencies, failure domains, and the minimum viable observability you need on day one."
                            ),
                            "pace_wpm": 152,
                            "emotion": "analytical_clear",
                        },
                    ],
                    "text_deep_dive": {
                        "summary_md": f"## {dom}\nFocus on **blast radius**, **data residency**, and **idempotent replay** when integrating.",
                        "flashcards": [
                            {"q": f"What is the primary failure domain for {dom}?", "a": "Cross-region policy + identity staleness"},
                            {"q": "Name two golden signals tied to customer journeys", "a": "Latency p99 and business error rate"},
                        ],
                    },
                },
            }
        )
    return out


def build_image_prompt_library(n: int) -> list:
    styles = ["isometric dark fintech", "blueprint schematic", "neon topology", "glass 3D layers", "minimal Swiss grid"]
    subjects = [
        "ledger double-entry flow",
        "UPI intent → PSP → CBS settlement",
        "fraud feature vector fan-out",
        "Temporal saga for loan disbursement",
        "HSM signing ceremony",
        "VKYC liveness pipeline",
        "open banking consent ledger",
        "Basel III reporting lineage",
        "ATM ISO8583 hop sequence",
        "MLOps model promotion gates",
    ]
    out = []
    for i in range(n):
        out.append(
            {
                "asset_id": f"IMG-{i+1:04d}",
                "training_track": ["platform", "security", "data", "mobile", "payments"][i % 5],
                "positive_prompt": (
                    f"{styles[i % len(styles)]} illustrating {subjects[i % len(subjects)]}; "
                    f"numbered stages; arrows; risk heat color coding; ultra sharp vector-like edges"
                ),
                "negative_prompt": "text overlay, logo watermark, blurry, childish, photorealistic humans",
                "recommended_aspect": ["16:9", "4:3", "1:1", "9:16"][i % 4],
                "accessibility_note": "Ensure 4.5:1 contrast for all labels; provide alt text from stage list",
            }
        )
    return out


def build_video_curriculum(episodes: int, scenes_per: int) -> list:
    themes = [
        "Zero-trust mesh for banking APIs",
        "Incident command for P1 payment outages",
        "Data contract governance in the lakehouse",
        "Mobile release trains & feature flags",
        "Synthetic monitoring across regions",
        "Model risk management for fraud ML",
    ]
    out = []
    for ep in range(episodes):
        scenes = []
        for sc in range(scenes_per):
            themes_idx = (ep + sc) % len(themes)
            scenes.append(
                {
                    "scene_id": f"EP{ep+1:02d}-S{sc+1:02d}",
                    "duration_sec": 12 + (sc % 6) * 3,
                    "visual_direction": (
                        f"Slow dolly through abstract {themes[themes_idx]} visualization; "
                        f"particle trails for requests; depth of field on critical path"
                    ),
                    "on_screen_text": [f"Beat {sc+1}", themes[themes_idx][:48]],
                    "voiceover_script": (
                        f"Scene {sc+1}: we stress-test assumptions behind {themes[themes_idx].lower()} — "
                        f"what breaks first, what we measure, and how we rehearse the fix."
                    ),
                    "music_bed": ["sub pulse ambient", "light arpeggio", "tension pad", "resolve major"][sc % 4],
                    "sfx_cues": ["soft whoosh transition", "UI click layer", "distant server hum"],
                    "color_grade": "teal-orange cinematic with desaturated backgrounds",
                    "caption_priority": "VO + on-screen KPIs",
                }
            )
        out.append(
            {
                "episode_id": f"VC-{ep+1:03d}",
                "title": f"Masterclass {ep+1}: {themes[ep % len(themes)]}",
                "total_runtime_target_sec": sum(s["duration_sec"] for s in scenes),
                "learning_objectives": [
                    "Relate architecture to measurable SLOs",
                    "Identify single points of coupling",
                    "Draft a credible rollback narrative",
                ],
                "prerequisite_modules": [f"TXT-{(ep % 50) + 1:04d}", f"TXT-{((ep + 3) % 50) + 1:04d}"],
                "scenes": scenes,
            }
        )
    return out


def build_audio_narration_library(n: int) -> list:
    out = []
    for i in range(n):
        out.append(
            {
                "track_id": f"AUD-{i+1:04d}",
                "title": f"Micro-lesson {i+1}: golden path narration",
                "voice_profile": {"gender": "neutral", "age": "adult", "tone": "mentor", "accent": "neutral_intl"},
                "script_with_pauses": (
                    f"[pause 0.4s] You are learning slice {i+1}. [pause 0.2s] "
                    f"Banks ship money and trust — your code sits on that chain. [pause 0.3s] "
                    f"Always ask: what audit artifact does this feature leave behind?"
                ),
                "mix_notes": {"duck_music_db": -14, "de_esser": True, "loudness_lufs": -16},
                "linked_visual_assets": [f"IMG-{(i % 200) + 1:04d}", f"IMG-{((i + 7) % 200) + 1:04d}"],
            }
        )
    return out


def build_text_curriculum_modules(n: int) -> list:
    out = []
    for i in range(n):
        out.append(
            {
                "module_id": f"TXT-{i+1:04d}",
                "title": f"Curriculum strand {i+1}: platform literacy",
                "reading_time_min": 8 + (i % 12),
                "objectives": [
                    "Explain how a change propagates from IDE to canary",
                    "Map a user story to owning services",
                    "List mandatory compliance checkpoints",
                ],
                "body_md": (
                    f"### Strand {i+1}\n\n"
                    "1. **Context**: Engineering here is socio-technical — code, contracts, and committees.\n"
                    "2. **Practice**: Trace one production alert to the owning service graph node.\n"
                    "3. **Reflection**: Write three failure modes your feature could introduce.\n\n"
                    "```mermaid\nflowchart LR\n  dev[Dev] --> ci[CI]\n  ci --> stg[Staging]\n  stg --> can[Canary]\n  can --> prod[Prod]\n```\n"
                ),
                "quiz": [
                    {
                        "question": "What must precede prod traffic on a new API?",
                        "options": ["Lint only", "Threat model + authZ review + SLO definition", "Marketing approval", "None"],
                        "answer": 1,
                        "rationale": "Regulated environments require explicit controls and measurable SLOs before exposure.",
                    },
                    {
                        "question": "Best artifact for cross-team alignment?",
                        "options": ["Slack thread", "Architecture decision record (ADR)", "Personal notes", "Verbal only"],
                        "answer": 1,
                        "rationale": "ADRs create durable, searchable decisions.",
                    },
                ],
                "hands_on_lab": {
                    "title": f"Lab {i+1}: synthetic trace",
                    "steps": [
                        "Clone sandbox service template",
                        "Inject OpenTelemetry span linking to CBS mock",
                        "Export trace JSON and annotate critical path",
                    ],
                },
            }
        )
    return out


def _role_seed(role: str) -> int:
    return int(hashlib.sha256(role.encode()).hexdigest()[:8], 16)


def build_role_media_matrix() -> dict:
    roles = [
        "Full Stack Developer",
        "SRE / Platform",
        "Data Engineer",
        "Security Engineer",
        "Mobile Engineer",
        "ML Engineer",
        "Product Engineer",
        "QA Automation",
    ]
    m = {}
    for r in roles:
        h = _role_seed(r)
        m[r] = {
            "priority_video_episodes": [f"VC-{((h + k) % 40) + 1:03d}" for k in range(6)],
            "priority_image_assets": [f"IMG-{((h + k * 3) % 180) + 1:04d}" for k in range(8)],
            "priority_audio_tracks": [f"AUD-{((h + k * 5) % 120) + 1:04d}" for k in range(5)],
            "text_modules_first_pass": [f"TXT-{((h + k) % 40) + 1:04d}" for k in range(10)],
        }
    return m


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(root, "banking_knowledge.json")

    data = {
        "meta": SEED["meta"],
        "systems": SEED["systems"] + gen_extra_systems(48),
        "teams": SEED["teams"]
        + [
            {"name": "Compliance Engineering", "responsibilities": ["KYC/AML", "Policy engines", "Audit tooling"], "owned_systems": ["kyc-service"], "head": "Rahul Kumar", "size": 28},
            {"name": "Cards Team", "responsibilities": ["Issuing", "Acquiring interfaces", "HSM ops"], "owned_systems": ["card-management"], "head": "Suresh Iyer", "size": 22},
            {"name": "Finance Technology", "responsibilities": ["Treasury", "ALM", "Market data"], "owned_systems": ["treasury-management"], "head": "Anita Rao", "size": 18},
            {"name": "Data Engineering", "responsibilities": ["Pipelines", "Warehouse", "BI"], "owned_systems": ["analytics-platform"], "head": "Kiran Joshi", "size": 40},
        ],
        "processes": {
            **SEED["processes"],
            "security_review": {
                "steps": ["STRIDE-lite threat model", "Dependency SBOM scan", "Secret scan", "Peer security +1", "Prod exception board if needed"],
                "sla_hours": 48,
            },
            "data_governance": {
                "steps": ["Classify dataset", "DPIA if PII", "Lineage registration", "Retention policy attach", "Access via ABAC"],
            },
        },
        "multimodal_training": {
            "generation_style_guide": {
                "image": SEED["meta"]["visual_brand"],
                "video": "1080p master, 24fps, subtle grain, motion <20% frame for readability of diagrams",
                "audio": SEED["meta"]["audio_brand"],
                "text": "Use concrete service names from systems[]; avoid generic banking platitudes",
            },
            "video_curriculum": build_video_curriculum(episodes=40, scenes_per=10),
            "image_prompt_library": build_image_prompt_library(220),
            "audio_narration_library": build_audio_narration_library(140),
            "text_curriculum_modules": build_text_curriculum_modules(55),
            "role_media_matrix": build_role_media_matrix(),
            "glossary": [
                {"term": t, "definition": f"Canonical definition for {t} in this synthetic corpus (cross-link to VC/AUD/IMG tracks)."}
                for t in (
                    "SLO error budget blast radius idempotency saga canary feature flag SPIFFE mTLS HSM PCI-DSS "
                    "Basel III ALM CKYC UPI NEFT RTGS IMPS SWIFT gpi PSD2 open banking consent vault "
                    "data lineage DPIA ABAC RBAC zero trust golden signals exemplars trace span"
                ).split()
            ],
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    sz = os.path.getsize(out_path)
    print(f"Wrote {out_path} ({sz / 1024 / 1024:.2f} MiB)")


if __name__ == "__main__":
    main()
