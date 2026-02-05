# Interactive UI Enhancements Design

**Date**: 2026-02-05
**Goal**: Make all components in standalone_ui feel more interactive with a fluid, professional experience.

---

## Summary

Add subtle hover feedback to all interactive elements and staggered animations for visual rhythm. The approach is professional and understated - gentle lifts, soft shadow increases, smooth transitions.

---

## Design Decisions

| Decision | Choice |
|----------|--------|
| Hover feedback level | Subtle (lift -2px, soft shadow, smooth transitions) |
| Scope | Everything interactive (cards, buttons, timeline, badges, tables, pills) |
| Timeline treatment | Mini-card feel on hover (shadow + lift) |
| Visual rhythm | Staggered cascade animations for results reveal |

---

## Implementation Details

### 1. Core Hover System

**Timing**: 150ms ease-out for snappy, responsive feel.

**Cards (results section)**:
- Default: `shadow-md`
- Hover: translateY(-2px), `shadow-lg`, subtle border highlight
- Transition: `transform 0.15s ease-out, box-shadow 0.15s ease-out`

**Buttons (reset, maximize, reload)**:
- Hover: background darkens, icon buttons scale 1.05
- Active (pressed): scale 0.95 for tactile feedback

### 2. Timeline Items (Mini-Card Treatment)

**Hover state**:
- Background: transparent → white with subtle shadow
- Lift: translateY(-2px)
- Left border: 2px → 3px
- Icon: scale 1.1

### 3. Smaller Interactive Elements

**Badges** (tool name, agent name):
- Hover: background darkens one shade, scale 1.03

**Table rows**:
- Hover: background highlight (`bg-gray-50` → `bg-gray-100`)

**Connection status pill**:
- Hover: border color transition, subtle glow

**Expandable details** (tool result accordions):
- Hover on summary: background highlight
- Open/close: smooth height transition

### 4. Staggered Animations

**Results cards cascade**:
- Sequential fade-in with 80-100ms delay between cards
- Each card: fade + slide up (translateY 10px → 0)

**Analysis cards with graphs**:
- Cards appear first, graphs fade in 150ms after

**Page load sequence**:
- Header → DAG section → Timeline container
- Total stagger: ~300ms

---

## Files to Modify

| File | Changes |
|------|---------|
| `static/css/styles.css` | Add hover states, transitions, stagger keyframes |
| `static/js/cards_renderer.js` | Apply stagger classes when rendering cards |
| `static/js/timeline_renderer.js` | Add interactive classes to timeline items |
| `static/js/demo_player.js` | Orchestrate stagger delays for results reveal |

---

## CSS Classes to Add

```css
/* Hover states */
.interactive-card      /* Cards: lift + shadow */
.interactive-btn       /* Buttons: hover/active states */
.interactive-row       /* Table rows: background highlight */
.interactive-badge     /* Badges: darken + scale */
.timeline-item-interactive  /* Timeline: mini-card hover */

/* Stagger utilities */
.stagger-fade-in       /* Base animation */
.stagger-delay-1 through .stagger-delay-6  /* Delay increments */
.cascade-reveal        /* Parent trigger for child stagger */
```

---

## No New Dependencies

Pure CSS transitions and animations with minimal JavaScript for applying delay classes dynamically.
