from app.agents.base_agent import BaseAgent


class BusinessAgent(BaseAgent):
    def create_research_brief(self, command: str) -> str:
        return f"""# Research Brief

## Command
{command}

## Market Assumptions
- Pakistan has an urban, social-media-driven food discovery market.
- Greek yogurt can be positioned around protein, gut health, breakfast, desserts, and fitness.
- The first controlled launch should validate demand before scaling operations.

## Customer Segments
- Fitness-focused young professionals seeking high-protein snacks.
- Parents looking for healthier breakfast or lunchbox options.
- Dessert buyers who want premium, lighter alternatives.
- Small office teams ordering recurring snack packs.

## Competitor Placeholders
- Local dairy brands and yogurt cups.
- Home bakers and dessert cup sellers on Instagram/Facebook.
- Imported or premium health food alternatives in major cities.

## Local Business Considerations
- Cash-on-delivery and WhatsApp-first ordering may matter more than a full checkout at launch.
- Cold-chain expectations, delivery radius, and shelf-life claims need human verification.
- Halal, nutrition, ingredient, and labeling claims need review before publication.

## Questions Requiring Verification
- Exact target city delivery costs and cold storage options.
- Local competitor pricing by cup size and bundle.
- Food registration, labeling, and safety requirements.
- Real supplier, production, and fulfillment constraints are intentionally out of scope for this run.
"""

    def create_content_calendar(self, command: str) -> str:
        return f"""# 14-Day Launch Content Calendar

## Positioning
Greek yogurt for Pakistan-based customers who want a premium, protein-rich, convenient snack without heavy dessert guilt.

## Calendar
| Day | Channel | Theme | Post Idea |
| --- | --- | --- | --- |
| 1 | Instagram | Teaser | "A thicker, cleaner snack is coming." |
| 2 | Facebook | Education | What makes Greek yogurt different? |
| 3 | Instagram Reels | Texture | Spoon pull / swirl shot with fruit topping. |
| 4 | Stories | Poll | Breakfast, dessert, or post-workout? |
| 5 | Instagram | Benefits | Protein, freshness, and portion control. |
| 6 | Facebook | Product | Flavor preview carousel. |
| 7 | Stories | Waitlist | Collect city and preferred flavor. |
| 8 | Instagram Reels | Use Case | Office snack cup routine. |
| 9 | Instagram | Social Proof | Share waitlist count or taste-test quote placeholder. |
| 10 | Facebook | FAQ | Delivery radius, ordering, storage guidance. |
| 11 | Stories | Countdown | 3 days until first order batch. |
| 12 | Instagram | Offer | Founder batch / limited slots announcement. |
| 13 | Stories | Order Flow | Show WhatsApp ordering steps. |
| 14 | Instagram + Facebook | Launch | "First batch is open." |

## Caption Starters
- "Thick, chilled, and made for snack cravings that still feel clean."
- "Your breakfast cup, dessert cup, and post-workout cup can finally be the same cup."
- "Founder batch is limited so we can keep every order fresh and controlled."

## Human Approval Needed
- Any nutrition, health, ingredient, halal, or shelf-life claims.
- Product photography and final pricing.
- Delivery radius and order cutoff time.
"""
