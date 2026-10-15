# Kaze review — Control Center unification

Creative-direction slice. I am answering the six prompts through feeling, and I am taking a position on the brand.

## The brand that wins

The coffee and cream wins. This is not close. The business is Beans and Co. The product sells beans. The indigo Control Center reads like a thousand other admin panels, and the owner already feels the seam: "ahora esta todo mezclado". Indigo is a stranger's house. Cream is their own counter. We keep the Control Center's structure, its grid, its mono numbers, its calm density, and we pour the legacy warmth over it. Coffee ink for text, cream for surface, a single roasted accent for the one thing that matters on each page. The indigo dies as a theme and survives only as spacing discipline. MEMORY law: the owner should feel they never left home, whether they are on Stock or Ventas or Resultado.

## 1. The problem

Two worlds pretending to be one product. The owner steps through the door and lands in the old house. The spec calls it unification, but the real wound is identity: the owner cannot tell where the product ends. We are not merging two pages. We are proving there is one place.

## 2. Smallest first version

M6 first, not last. Extract one shared shell with the coffee tokens before any new page ships. Then M1 Productos rides that shell. One page that breathes in the real brand proves the whole idea in a day. Shipping four indigo pages and re-skinning later means the owner watches us build the seam we promised to remove.

## 3. Three risks

- **Re-skin instead of re-root.** If tokens are not extracted first, every page hardcodes its own color and M6 becomes a graveyard of find-replace. The shell is the architecture.
- **Bounce physics.** Tiles that reload the whole document between home and detail read as a set of bounces, not one surface. Without a held nav and a soft page transition, unification is a claim, not a feeling.
- **Empty states that apologize.** New pages with no data will say "error" or show nothing. SILENCE law broken. An empty Stock page is an invitation to add the first product, not a failure.

## 4. Success at 90 days

The owner opens the door, never sees indigo, never sees the old view, and cannot point to where one page ends and the next begins. Caja and stock numbers greet them in mono the instant the page settles. Nobody mentions "the old page" because nobody reaches it.

## 5. Atomic tasks (feel slice)

1. Define coffee/cream token set (ink, cream surface, one roasted accent, border-as-whisper) in one CSS file. (1d)
2. Build shared Control Center shell: header, held nav rail, slot. Legacy base.html retired from owner paths. (1d)
3. Port control_center.html home onto the shell with new tokens. (1d)
4. Shared page-enter transition, 400ms cubic-bezier(0.16,1,0.3,1), y-offset 20px. (0.5d)
5. PRESENCE pass: caja and stock figures as fortissimo mono, settle-in on load. (0.5d)
6. SILENCE pass: one empty-state component, invitation copy, shared across pages. (0.5d)
7. Skeleton loaders echoing each page layout, honoring the fail-open degraded state. (1d)
8. Timonel widget restyled to coffee tokens, docked in the shell. (0.5d)

## 6. The one thing only my faculty noticed

The bounce IS the mixing. Dario said "todo mezclado" because clicking a tile throws him across a brand boundary mid-task. Even after every page turns coffee, if each tile does a full document reload with no held nav and no transition, he will still feel two places. Fix the transition and the shell, and the two worlds become one surface before a single CRUD form is built.
