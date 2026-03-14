"""
Birthday & Gift Planner Pipeline — tracks upcoming birthdays from the
relationships table, surfaces preference prompts, and suggests gifts
using Claude based on accumulated taste history.

Relationship schema:
  relationships            — core contact record with birthday
  relationship_preferences — evolving tastes (logged over time)
  relationship_interactions — communication history
  gifts                    — gift ideas, orders, and reactions
"""
import logging
from datetime import date, datetime, timedelta

import anthropic

from app.config import Config
from app.db import get_conn

logger = logging.getLogger(__name__)

PREFERENCE_CATEGORIES = [
    "food & restaurants", "hobbies & activities", "books & media",
    "fashion & style", "home & decor", "tech & gadgets",
    "sports & fitness", "travel & experiences", "music & entertainment",
    "colors & aesthetics", "brands", "wishlist items",
]

UPCOMING_DAYS = 30   # alert window
PROMPT_DAYS   = 21   # start prompting for preference updates


class BirthdayPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    # ── Public ────────────────────────────────────────────────────────────────

    def get_upcoming_birthdays(self) -> dict:
        """Return all birthdays within UPCOMING_DAYS with preference summaries."""
        birthdays = self._fetch_upcoming_birthdays()
        enriched = []
        for b in birthdays:
            prefs = self._get_preferences(b["id"])
            recent_gifts = self._get_recent_gifts(b["id"])
            b["preferences"] = prefs
            b["recent_gifts"] = recent_gifts
            b["needs_preference_update"] = self._needs_update(b, prefs)
            b["gift_suggestions"] = []  # populated on demand
            enriched.append(b)

        # Create action items for approaching birthdays
        self._create_birthday_action_items(enriched)

        return {
            "upcoming_birthdays": enriched,
            "total": len(enriched),
            "needs_update": [b["name"] for b in enriched if b["needs_preference_update"]],
        }

    def get_gift_suggestions(self, relationship_id: int, budget: str = "any") -> dict:
        """Ask Claude for personalized gift ideas based on logged preferences."""
        person = self._get_relationship(relationship_id)
        if not person:
            return {"error": "Relationship not found"}

        prefs = self._get_preferences(relationship_id)
        past_gifts = self._get_recent_gifts(relationship_id, limit=10)

        suggestions = self._generate_gift_ideas(person, prefs, past_gifts, budget)

        # Log gift suggestions as 'idea' status
        for s in suggestions:
            self._save_gift(
                relationship_id=relationship_id,
                occasion="birthday",
                occasion_date=self._next_birthday(person.get("birthday")),
                description=s.get("gift"),
                status="idea",
                price=s.get("estimated_price"),
                purchase_url=s.get("purchase_url", ""),
            )

        return {
            "person": person["name"],
            "suggestions": suggestions,
            "based_on_preferences": len(prefs),
            "past_gifts_excluded": [g["gift_description"] for g in past_gifts],
        }

    def log_preference(self, relationship_id: int, category: str,
                       preference: str, source: str = "manual") -> dict:
        """Record a new or updated preference for a person."""
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO relationship_preferences "
                "(relationship_id, category, preference, source, confidence) "
                "VALUES (%s, %s, %s, %s, 8)",
                (relationship_id, category, preference, source),
            )
            # Update relationship updated_at
            cur.execute(
                "UPDATE relationships SET updated_at=NOW() WHERE id=%s",
                (relationship_id,),
            )
            cur.close()
            conn.close()
            logger.info("Logged preference for rel %s: [%s] %s", relationship_id, category, preference)
            return {"success": True, "relationship_id": relationship_id, "category": category}
        except Exception as e:
            logger.error("Log preference failed: %s", e)
            return {"error": str(e)}

    def log_gift(self, relationship_id: int, occasion: str, description: str,
                 status: str = "given", price: float = None,
                 reaction: str = "", purchase_url: str = "") -> dict:
        """Record a gift given or planned."""
        occasion_date = self._next_birthday(
            self._get_relationship(relationship_id).get("birthday")
        ) if occasion == "birthday" else None
        self._save_gift(relationship_id, occasion, occasion_date,
                        description, status, price, reaction, purchase_url)
        return {"success": True}

    def log_interaction(self, relationship_id: int, interaction_type: str,
                        summary: str, sentiment: str = "neutral") -> dict:
        """Log a communication or event with a person."""
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO relationship_interactions "
                "(relationship_id, type, summary, sentiment) VALUES (%s,%s,%s,%s)",
                (relationship_id, interaction_type, summary, sentiment),
            )
            cur.execute(
                "UPDATE relationships SET last_contacted=NOW() WHERE id=%s",
                (relationship_id,),
            )
            cur.close()
            conn.close()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def create_relationship(self, name: str, email: str = "", birthday: str = "",
                            relationship_type: str = "family",
                            notes: str = "", is_family: bool = False) -> dict:
        """Add a new person to the relationship table."""
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO relationships (name, email, birthday, relationship_type, notes, is_family) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (name, email or None, birthday or None, relationship_type, notes, 1 if is_family else 0),
            )
            rel_id = cur.lastrowid
            cur.close()
            conn.close()
            return {"success": True, "id": rel_id, "name": name}
        except Exception as e:
            return {"error": str(e)}

    def get_full_profile(self, relationship_id: int) -> dict:
        """Return complete relationship profile: person + prefs + gifts + interactions."""
        person = self._get_relationship(relationship_id)
        if not person:
            return {"error": "Not found"}
        return {
            "person": person,
            "preferences": self._get_preferences(relationship_id),
            "gifts": self._get_recent_gifts(relationship_id, limit=20),
            "interactions": self._get_interactions(relationship_id, limit=20),
            "days_until_birthday": self._days_until_birthday(person.get("birthday")),
            "preference_categories": PREFERENCE_CATEGORIES,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch_upcoming_birthdays(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT id, name, email, birthday, relationship_type, notes,
                          DATEDIFF(
                            DATE(CONCAT(YEAR(CURDATE()),'-',
                                 LPAD(MONTH(birthday),2,'0'),'-',
                                 LPAD(DAY(birthday),2,'0'))),
                            CURDATE()
                          ) AS days_away
                   FROM relationships
                   WHERE birthday IS NOT NULL
                     AND DATEDIFF(
                           DATE(CONCAT(YEAR(CURDATE()),'-',
                                LPAD(MONTH(birthday),2,'0'),'-',
                                LPAD(DAY(birthday),2,'0'))),
                           CURDATE()
                         ) BETWEEN 0 AND %s
                   ORDER BY days_away ASC""",
                (UPCOMING_DAYS,),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Fetch upcoming birthdays failed: %s", e)
            return []

    def _get_relationship(self, rel_id: int) -> dict | None:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM relationships WHERE id=%s", (rel_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return row
        except Exception:
            return None

    def _get_preferences(self, rel_id: int) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT category, preference, recorded_at, source, confidence "
                "FROM relationship_preferences "
                "WHERE relationship_id=%s AND is_active=1 "
                "ORDER BY confidence DESC, recorded_at DESC",
                (rel_id,),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception:
            return []

    def _get_recent_gifts(self, rel_id: int, limit: int = 5) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT occasion, occasion_date, gift_description, status, price, reaction "
                "FROM gifts WHERE relationship_id=%s "
                "ORDER BY occasion_date DESC LIMIT %s",
                (rel_id, limit),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception:
            return []

    def _get_interactions(self, rel_id: int, limit: int = 20) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT type, summary, sentiment, interaction_at "
                "FROM relationship_interactions WHERE relationship_id=%s "
                "ORDER BY interaction_at DESC LIMIT %s",
                (rel_id, limit),
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception:
            return []

    def _needs_update(self, person: dict, prefs: list[dict]) -> bool:
        if person.get("days_away", 99) > PROMPT_DAYS:
            return False
        if len(prefs) < 3:
            return True
        if not prefs:
            return True
        latest = max(prefs, key=lambda p: str(p.get("recorded_at", "")))
        recorded = str(latest.get("recorded_at", ""))[:10]
        try:
            age = (date.today() - date.fromisoformat(recorded)).days
            return age > 180  # prompt if last update was 6+ months ago
        except Exception:
            return True

    def _generate_gift_ideas(self, person: dict, prefs: list[dict],
                              past_gifts: list[dict], budget: str) -> list[dict]:
        pref_text = "\n".join(
            f"  [{p['category']}]: {p['preference']}" for p in prefs
        ) or "  (no preferences recorded yet)"

        past_text = "\n".join(
            f"  - {g['occasion']} {g.get('occasion_date','')}: {g['gift_description']}"
            f"{' — reaction: '+g['reaction'] if g.get('reaction') else ''}"
            for g in past_gifts
        ) or "  (no prior gifts recorded)"

        prompt = f"""Generate 5 personalized, thoughtful gift ideas for {person['name']}.

Known preferences:
{pref_text}

Past gifts (do NOT repeat these):
{past_text}

Budget: {budget}
Occasion: birthday

Return a JSON array of 5 objects:
[{{"gift": "specific gift name/description", "reason": "why they'll love it based on their preferences",
   "estimated_price": "$XX-$XX", "purchase_url": "suggested search or site", "category": "category"}}]

Return ONLY the JSON array."""

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.error("Gift suggestion failed: %s", e)
            return []

    def _save_gift(self, relationship_id, occasion, occasion_date,
                   description, status, price=None, reaction="", purchase_url=""):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO gifts (relationship_id, occasion, occasion_date, "
                "gift_description, status, price, reaction, purchase_url) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (relationship_id, occasion, occasion_date, description,
                 status, price, reaction, purchase_url),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Save gift failed: %s", e)

    def _create_birthday_action_items(self, birthdays: list[dict]):
        """Create action items in the DB for approaching birthdays."""
        try:
            conn = get_conn()
            cur = conn.cursor()
            for b in birthdays:
                days = b.get("days_away", 99)
                if days > PROMPT_DAYS:
                    continue
                priority = 1 if days <= 3 else (2 if days <= 7 else 3)
                title = (
                    f"🎂 {b['name']}'s birthday is {'TODAY!' if days == 0 else f'in {days} day(s)!'}"
                )
                detail = (
                    f"Send a birthday message to {b['name']}."
                    + (" Update their preferences first — profile is sparse." if b.get("needs_preference_update") else "")
                )
                cur.execute(
                    "INSERT INTO action_items (priority, title, detail, action_type, recipient) "
                    "VALUES (%s, %s, %s, 'email', %s)",
                    (priority, title, detail, b.get("email", "")),
                )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Birthday action items failed: %s", e)

    def _next_birthday(self, birthday_str) -> str | None:
        if not birthday_str:
            return None
        try:
            bday = date.fromisoformat(str(birthday_str)[:10])
            today = date.today()
            next_bd = bday.replace(year=today.year)
            if next_bd < today:
                next_bd = next_bd.replace(year=today.year + 1)
            return next_bd.isoformat()
        except Exception:
            return None

    def _days_until_birthday(self, birthday_str) -> int | None:
        nxt = self._next_birthday(birthday_str)
        if not nxt:
            return None
        return (date.fromisoformat(nxt) - date.today()).days
