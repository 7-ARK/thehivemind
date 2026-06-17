from app.agents.base_agent import BaseAgent


class OperationsAgent(BaseAgent):
    def create_operations_checklist(self, command: str) -> str:
        return f"""# Operations Checklist

## Command
{command}

## Order Flow
1. Customer sees launch content.
2. Customer opens WhatsApp/order form.
3. Customer selects cup size, flavor, quantity, delivery area, and preferred slot.
4. Admin confirms availability, delivery fee, and payment method.
5. Customer receives confirmation message and order ID.
6. Team prepares batch list and delivery handoff list.
7. Customer receives delivery update and post-delivery feedback prompt.

## WhatsApp Handling Process
- Use saved quick replies for pricing, flavors, delivery radius, and storage guidance.
- Require manual approval before confirming any custom order.
- Tag conversations by status: new lead, awaiting payment, confirmed, packed, delivered, feedback.

## Backend / Website Feature List
- Landing page with offer, product sizes, FAQs, and WhatsApp CTA.
- Admin order table with status changes and manual notes.
- Simple product/flavor configuration.
- Delivery area and fee configuration.
- Exportable daily batch sheet.
- Feedback capture form.

## Customer Journey
- Awareness: social posts and reels.
- Interest: benefits, flavors, and founder batch scarcity.
- Conversion: WhatsApp/order form.
- Fulfillment: manual confirmation and delivery.
- Retention: reorder prompt and flavor voting.

## Manual Approval Steps
- Pricing before launch.
- Delivery radius and fees.
- Any health/nutrition claims.
- Refund/replacement policy.
- Daily maximum order capacity.
"""
