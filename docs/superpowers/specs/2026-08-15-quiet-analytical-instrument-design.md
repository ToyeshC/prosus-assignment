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
- “Quiet interface, kinetic moments” supersedes an overly bare interpretation of the quiet-instrument direction: the resting UI is calm and analytical, while direct interactions acknowledge themselves with restrained motion that stops when results arrive.
- The approved visual reference is `quiet-kinetic-analytics-concept.html`; reproduce its composition and visual language in Streamlit without treating its sample data or chart type as application data.
- Use a barely perceptible dot-grid ambient canvas; it provides structural texture without acting as an animated or decorative background.
- Keep compact tactile header controls, including initials avatars for demo-session identity, and silent successful authorization.
- Multiple-source selection uses clearly interactive, full-width source rows with an arrow, small hover/focus accent response, and modest positional feedback—not dashboard cards.
- The query composer places Options before the accent Run control. Examples remain lightweight actions. Preserve the canonical `question_draft` and `submitted_question` distinction.
- While a real synchronous run is in progress, replace the small inline spinner with a central, general-purpose loading state: an animated mark, “Analysing {database}”, and “Preparing your result…”. It must honor reduced-motion preferences, never imply fabricated agent stages, and disappear when the result becomes available.
- Give successful answers and their existing, agent-selected visualization stronger typographic and spatial authority. Keep the chart integrated with the canvas and technical evidence under Run details only.
- Renderer-only presentation formatting prevents floating-point artefacts, uses suitable separators and decimal precision, and applies currency formatting only when the existing trustworthy label/context supports it. Underlying `AnalysisResult` values remain unchanged.
- For a ranked categorical visualization with high cardinality, show only the leading approximately 10–12 categories in the chart and disclose the display limit. Preserve the complete result in Data. Do not apply this temporal, distribution, or relationship charts; retain existing Pie/Donut readability behavior.
- Avoid decorative palettes, gradients, excessive cards, pills, borders, rounded boxes, uppercase tracked labels, and middot-heavy operational copy.
- Typography, alignment, whitespace, data formatting, and charts provide the polish. Monospace is reserved for technical details.
- Preserve all existing information capabilities. Do not alter backend, agent, governance, evaluation, SQL, database, onboarding, or analytical behavior.
