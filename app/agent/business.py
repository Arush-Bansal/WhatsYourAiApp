"""Structured business knowledge for the WhatsApp agent (single-tenant default)."""

from __future__ import annotations

from dataclasses import dataclass

# Section keys accepted by get_business_details / BusinessInfo.section
BUSINESS_DETAIL_SECTIONS = (
    "overview",
    "services",
    "hours",
    "pricing",
    "insurance",
    "faqs",
    "booking",
    "contact",
    "all",
)


@dataclass(frozen=True)
class Service:
    name: str
    description: str
    price_inr: str


@dataclass(frozen=True)
class FAQ:
    question: str
    answer: str


@dataclass(frozen=True)
class BusinessInfo:
    name: str
    tagline: str
    dentist_name: str
    qualifications: str
    address: str
    phone: str
    email: str
    hours: dict[str, str]
    services: list[Service]
    insurances_accepted: list[str]
    booking_instructions: str
    emergency_contact: str
    faqs: list[FAQ]
    service_scope_line: str

    def _hours_compact(self) -> str:
        """Single-line summary for the system prompt."""
        order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        parts: list[str] = []
        for day in order:
            if day in self.hours:
                parts.append(f"{day[:3]} {self.hours[day]}")
        return "; ".join(parts) if parts else "Hours on request"

    def overview(self) -> str:
        """Basics always injected into the system prompt."""
        lines = [
            f"Clinic: {self.name}",
            f"Tagline: {self.tagline}",
            f"Dentist: {self.dentist_name} ({self.qualifications})",
            f"Address: {self.address}",
            f"Phone: {self.phone}",
            f"Email: {self.email}",
            f"Hours (summary): {self._hours_compact()}",
            f"Scope: {self.service_scope_line}",
            "",
            "For full lists (pricing, per-day hours, insurance, FAQs, booking steps, emergency), "
            "call get_business_details with one of: "
            + ", ".join(s for s in BUSINESS_DETAIL_SECTIONS if s != "all")
            + ", or all.",
        ]
        return "\n".join(lines)

    def section(self, key: str) -> str:
        k = key.strip().lower()
        if k == "overview":
            return self.overview()
        if k == "services":
            blocks = []
            for s in self.services:
                blocks.append(f"- {s.name}: {s.description}")
            return "Services:\n" + ("\n".join(blocks) if blocks else "(none)")
        if k == "pricing":
            blocks = []
            for s in self.services:
                blocks.append(f"- {s.name}: {s.price_inr}")
            return "Pricing (indicative, confirm at visit):\n" + "\n".join(blocks)
        if k == "hours":
            order = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            lines = ["Hours (by day):"]
            for day in order:
                if day in self.hours:
                    lines.append(f"- {day}: {self.hours[day]}")
            return "\n".join(lines)
        if k == "insurance":
            lines = ["Accepted insurance / plans (subject to verification):"]
            for ins in self.insurances_accepted:
                lines.append(f"- {ins}")
            return "\n".join(lines) if self.insurances_accepted else "No insurers listed."
        if k == "faqs":
            blocks = []
            for faq in self.faqs:
                blocks.append(f"Q: {faq.question}\nA: {faq.answer}")
            return "FAQs:\n\n" + ("\n\n".join(blocks) if blocks else "(none)")
        if k == "booking":
            return "How to book:\n" + self.booking_instructions.strip()
        if k == "contact":
            return (
                "Contact\n"
                f"- Clinic: {self.name}\n"
                f"- Address: {self.address}\n"
                f"- Phone: {self.phone}\n"
                f"- Email: {self.email}\n"
                f"- Emergency / after-hours: {self.emergency_contact}"
            )
        if k == "all":
            parts = [
                self.section("overview"),
                "---",
                self.section("services"),
                "---",
                self.section("pricing"),
                "---",
                self.section("hours"),
                "---",
                self.section("insurance"),
                "---",
                self.section("booking"),
                "---",
                self.section("contact"),
                "---",
                self.section("faqs"),
            ]
            return "\n".join(parts)
        return f"Unknown section: {key!r}. Use one of: {', '.join(BUSINESS_DETAIL_SECTIONS)}."


DENTAL_PRACTICE = BusinessInfo(
    name="Bright Smile Dental",
    tagline="Gentle care for every smile",
    dentist_name="Dr. Priya Sharma",
    qualifications="BDS, MDS (Orthodontics)",
    address="42 Jawahar Nagar, New Delhi 110007, India",
    phone="+91 11 2345 6789",
    email="hello@brightsmile.example",
    hours={
        "Monday": "10:00–19:00",
        "Tuesday": "10:00–19:00",
        "Wednesday": "10:00–19:00",
        "Thursday": "10:00–19:00",
        "Friday": "10:00–19:00",
        "Saturday": "10:00–14:00",
        "Sunday": "Closed",
    },
    service_scope_line=(
        "General, preventive, cosmetic, orthodontic, and pediatric dentistry "
        "(cleanings, fillings, root canals, braces/clear aligners, whitening, extractions)."
    ),
    services=[
        Service(
            name="Dental cleaning & exam",
            description="Scaling, polish, and oral health check.",
            price_inr="from ₹1,200",
        ),
        Service(
            name="Tooth-colored filling",
            description="Composite restoration for cavities.",
            price_inr="₹1,500–3,500 per tooth",
        ),
        Service(
            name="Root canal treatment",
            description="Single-visit or multi-visit endodontic care as needed.",
            price_inr="₹4,000–12,000 per tooth (varies by tooth)",
        ),
        Service(
            name="Braces / aligners consult",
            description="Assessment and treatment planning for orthodontics.",
            price_inr="Consult ₹800; treatment quoted after scan",
        ),
        Service(
            name="Teeth whitening",
            description="In-office or take-home options.",
            price_inr="from ₹8,000",
        ),
        Service(
            name="Kids dental visit",
            description="Exam, fluoride, and preventive guidance for children.",
            price_inr="from ₹900",
        ),
    ],
    insurances_accepted=[
        "Star Health (cashless subject to approval)",
        "Care Health — reimbursement",
        "Niva Bupa — select plans",
        "CGHS / ECHS — by referral where applicable",
    ],
    booking_instructions=(
        "Reply here with your preferred day and morning/evening. "
        "We confirm slots within one business day. "
        "First visit: bring a valid ID; arrive 10 minutes early for forms. "
        "Cancellation: please message at least 24 hours in advance."
    ),
    emergency_contact="+91 98XXX XXXXX (dentist on call after hours; "
    "for life-threatening issues dial 112 / visit ER)",
    faqs=[
        FAQ(
            question="Do you treat children?",
            answer="Yes. We offer pediatric exams and preventive care; anxious kids welcome.",
        ),
        FAQ(
            question="Is treatment painful?",
            answer="We use local anesthesia when needed and work at your pace to keep you comfortable.",
        ),
        FAQ(
            question="Do you offer payment plans?",
            answer="Installments may be available for orthodontic treatment; ask at consult.",
        ),
    ],
)
