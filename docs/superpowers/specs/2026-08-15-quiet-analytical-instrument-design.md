# Quiet Analytical Instrument UI Polish

## Purpose

Refine the Streamlit command center into a quiet analytical instrument. This is a presentation and interaction pass only: no changes to backend behavior, agents, governance, evaluation, SQL, or analysis semantics.

## Workspace

- Use a Utility Header Workspace as the resting state; there is no permanent sidebar.
- Keep the analytical workspace visually dominant: question, answer, data, and chart receive the page's primary space.
- Put identity and selected database in a compact header. Keep deeper context configuration behind progressive disclosure.

## Identity and access

- Treat identity selection as changing a demo session, not filtering data.
- Changing identity clears question, result, visualization, and context state, then recomputes accessible databases.
- Select a database automatically only when exactly one source is available. With multiple sources, require an explicit database choice; with none, show the intentional Donné no-source state.
- A successful ACL decision is silent. Denied, unavailable, and no-source states remain explicit when useful.

## Query, results, and evidence

- Keep the question field analytical rather than chat-like, with an adjacent Run action and lightweight examples.
- Keep Analysis lens and Visualization available through a discoverable Options surface without competing with the query.
- Answer, chart, and data dominate. Inline result context contains only human-useful scope.
- Prefer a clearly available time range, then an existing trustworthy display label with safe pluralization, and finally a neutral row/result count. Do not reinterpret raw dimensions into business concepts.
- Keep authorization, repairs, timing, agents, SQL, policy, provenance, and trace-safe metadata in Run details only.

## Visual system and boundaries

- Use a neutral near-white or cool-grey base, near-black ink, and one restrained accent. Green and red are semantic only.
- Avoid decorative palettes, gradients, excessive cards, pills, borders, rounded boxes, uppercase tracked labels, and middot-heavy operational copy.
- Typography, alignment, whitespace, data formatting, and charts provide the polish. Monospace is reserved for technical details.
- Preserve all existing information capabilities. Do not alter backend, agent, governance, evaluation, SQL, database, onboarding, or analytical behavior.
