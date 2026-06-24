# Platform UI Acceptance Checklist (1920x1080)

## Layout Constants

All measurements are in CSS pixels at 100% scale on a 1920x1080 display.

| Element         | Size (px)    | Description                           |
|-----------------|--------------|---------------------------------------|
| appBar          | 56           | Top application bar                    |
| primaryNav      | 216 / 64     | Left navigation (expanded / collapsed) |
| pageHeader      | 64           | Page title + action bar                |
| subNav          | 48           | Secondary tab bar below page header   |
| statusBar       | 28           | Bottom status bar                     |
| taskDrawer      | 480          | Right-side task detail drawer         |
| contentMargin   | 24           | Padding around main content area      |
| cardGap         | 16           | Gap between grid cards                |

Derived layout regions on a 1920x1080 screen:

| Region              | X      | Y       | Width            | Height    |
|---------------------|--------|---------|------------------|-----------|
| appBar              | 0      | 0       | 1920             | 56        |
| primaryNav (exp)    | 0      | 56      | 216              | 996       |
| primaryNav (coll)   | 0      | 56      | 64               | 996       |
| main content        | 216    | 56      | 1704             | 996       |
| main (nav coll)     | 64     | 56      | 1856             | 996       |
| pageHeader          | 216    | 56      | 1704             | 64        |
| content area        | 216+24 | 56+64+24| 1704-48          | 996-64-56 |
| statusBar           | 0      | 1052    | 1920             | 28        |
| taskDrawer          | 1440   | 56      | 480              | 996       |

**Acceptance criteria:** All UI pages at 1920x1080 must adhere to these
dimensions within a 2-pixel tolerance.  The content area must scroll
independently when content exceeds viewport.

---

## Per-Page Checkpoints

---

### 1. Project Page (`/project`)

| Widget                | Approx Position            | Expected Size      | Notes                         |
|-----------------------|----------------------------|--------------------|-------------------------------|
| appBar                | top edge                   | 1920 x 56          | Project name shown in center  |
| primaryNav            | left edge, below appBar    | 216 x 996          | Highlighted "Project" item    |
| pageHeader            | main area top              | 1704 x 64          | Title: "Project"              |
| New Project card      | content area, left-aligned | ~320 x 180         | Icon + "New Project" + CTA    |
| Open Project card     | cardGap right of New       | ~320 x 180         | Recent projects list          |
| Recent projects list  | below cards                | full content width | 3-5 recent entries            |
| project list item     | within list                | full width x ~56   | Name, path, date              |
| statusBar             | bottom edge                | 1920 x 28          | Version, last opened          |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, statusBar dimensions match layout table
- [ ] New Project / Open Project cards are ~320x180 with 16px gap
- [ ] Recent projects list renders below cards
- [ ] Scrollbar appears when 6+ recent projects
- [ ] No horizontal overflow on the page

---

### 2. Data Page (`/data`)

| Widget                 | Approx Position          | Expected Size    | Notes                          |
|------------------------|--------------------------|------------------|--------------------------------|
| appBar                 | top edge                 | 1920 x 56        |                                |
| primaryNav             | left edge                | 216 x 996        | "Data" item highlighted        |
| pageHeader             | main area top            | 1704 x 64        | "Data" + Import/Refresh btns   |
| filter bar             | below pageHeader         | ~1704 x 40       | Search, group, status filters  |
| asset grid / table     | below filter bar         | remaining area   | Thumbnails or table view       |
| asset card (thumbnail) | within grid              | ~200 x 200       | Image thumbnail + filename     |
| pagination bar         | bottom of content        | ~1704 x 36       | Page numbers, total count      |
| import button          | pageHeader right side    | ~120 x 32        | Primary CTA                    |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, statusBar dimensions match layout table
- [ ] Asset grid has 4 columns minimum at 1920px width
- [ ] Each thumbnail card is ~200x200 with 16px gap
- [ ] Filter bar is sticky below pageHeader
- [ ] Pagination bar at bottom updates correctly
- [ ] Large image assets (>2000px dimension) show "LARGE" badge
- [ ] Empty state shows "Import assets to begin" illustration

---

### 3. Import Page (`/import`)

| Widget                    | Approx Position         | Expected Size    | Notes                        |
|---------------------------|-------------------------|------------------|------------------------------|
| appBar                    | top edge                | 1920 x 56        |                              |
| primaryNav                | left edge               | 216 x 996        |                              |
| pageHeader                | main area top           | 1704 x 64        | "Import Data"                |
| drop zone                 | center of content       | ~600 x 300       | Drag-and-drop area           |
| file picker button        | inside drop zone        | ~200 x 40        | "Browse Files"               |
| import options panel      | right of drop zone      | ~400 x 300       | Format, group, duplicate     |
| progress bar              | below drop zone         | ~1200 x 24       | Visible during import        |
| import log / results      | below progress          | full width       | Success/error file list      |

**Acceptance:**
- [ ] Layout matches dimension spec
- [ ] Drop zone accepts drag-and-drop of image files
- [ ] Progress bar animates during import
- [ ] Import log shows per-file status (success, skipped, error)
- [ ] Error files show human-readable message
- [ ] Import complete state shows count summary

---

### 4. Label Page (`/label`)

| Widget                 | Approx Position          | Expected Size    | Notes                        |
|------------------------|--------------------------|------------------|------------------------------|
| appBar                 | top edge                 | 1920 x 56        |                              |
| primaryNav             | left edge                | 216 x 996        | "Label" item highlighted     |
| pageHeader             | main area top            | 1704 x 64        | "Label" + task family        |
| annotation canvas      | center of content        | remaining area   | Zoomable image canvas        |
| tool palette           | left of canvas           | ~48 x 400        | Vertical tool icons          |
| label list panel       | right of canvas          | ~280 x full      | Shape list + properties      |
| zoom controls          | canvas bottom-right      | ~120 x 32        | +/- zoom, fit-to-window      |
| navigation arrows      | canvas left/right edges  | ~32 x 32 each    | Previous/next asset          |
| asset counter          | pageHeader right side    | ~160 x 32        | "12 / 45" asset position     |

**Acceptance:**
- [ ] Layout matches dimension spec
- [ ] Canvas fills available space between panels
- [ ] Tool palette shows active tool highlighted
- [ ] Label list panel scrolls independently
- [ ] Zoom controls functional at all zoom levels
- [ ] Navigation arrows cycle through assets
- [ ] Canvas camera handles large images (>8000px) without jank

---

### 5. Preprocess Page (`/preprocess`)

| Widget                    | Approx Position         | Expected Size    | Notes                       |
|---------------------------|-------------------------|------------------|-----------------------------|
| appBar                    | top edge                | 1920 x 56        |                             |
| primaryNav                | left edge               | 216 x 996        | "Preprocess" item highlight |
| pageHeader                | main area top           | 1704 x 64        | "Preprocess" + Run button   |
| subNav                    | below pageHeader        | 1704 x 48        | "Config / Preview / History"|
| config panel (left)       | below subNav            | ~500 x remaining | Split strategy, tile params |
| preview panel (right)     | right of config         | ~1156 x remaining | Sample visualization        |
| run button                | pageHeader right side   | ~140 x 32        | Primary action               |
| output path selector      | config panel top        | ~full width x 36 | "Output: dataset_builds/"   |
| tile config group         | config panel            | ~full width      | Tile width, height, overlap |
| split config group        | config panel            | ~full width      | Train/val/test ratios       |
| run history table         | subNav "History" tab    | full content     | Previous build records      |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, subNav dimensions match layout table
- [ ] Config panel (left) is ~500px wide; preview (right) fills remaining
- [ ] Tile configuration fields accept valid integer ranges
- [ ] Split ratios auto-normalize to 1.0
- [ ] Preview panel updates when config changes
- [ ] Run History tab shows table with all previous builds
- [ ] Run button disabled when no annotated assets exist

---

### 6. Train Page (`/train`)

| Widget                 | Approx Position          | Expected Size    | Notes                       |
|------------------------|--------------------------|------------------|-----------------------------|
| appBar                 | top edge                 | 1920 x 56        |                             |
| primaryNav             | left edge                | 216 x 996        | "Train" item highlighted    |
| pageHeader             | main area top            | 1704 x 64        | "Train" + Start button      |
| subNav                 | below pageHeader         | 1704 x 48        | "Config / Monitor / History"|
| config panel (left)    | below subNav             | ~500 x remaining | Adapter selection, params   |
| monitor panel (right)  | right of config          | ~1156 x remaining | Loss curves, metrics       |
| adapter dropdown       | config panel top         | ~full x 36       | Model adapter selector      |
| dataset build selector | config panel             | ~full x 36       | Latest completed build      |
| hyperparams group      | config panel             | ~full x 200      | Epochs, batch, LR           |
| start training button  | pageHeader right side    | ~140 x 32        | Primary action               |
| loss chart             | monitor panel            | remaining area   | Real-time training curves   |
| run history table      | subNav "History" tab     | full content     | Previous run records        |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, subNav dimensions match layout table
- [ ] Config panel (left) ~500px; monitor panel (right) fills remaining
- [ ] Dataset build selector shows only completed builds
- [ ] Start button disabled when no completed dataset build
- [ ] Monitor panel shows "No active run" when idle
- [ ] Run History tab shows status badges (completed/running/failed)
- [ ] Training can be stopped mid-run

---

### 7. Evaluate Page (`/evaluate`)

| Widget                 | Approx Position          | Expected Size    | Notes                        |
|------------------------|--------------------------|------------------|------------------------------|
| appBar                 | top edge                 | 1920 x 56        |                              |
| primaryNav             | left edge                | 216 x 996        | "Evaluate" item highlighted  |
| pageHeader             | main area top            | 1704 x 64        | "Evaluate" + Run button     |
| subNav                 | below pageHeader         | 1704 x 48        | "Config / Results / History" |
| config panel (left)    | below subNav             | ~500 x remaining | Run + dataset selectors      |
| results panel (right)  | right of config          | ~1156 x remaining | Metric cards, confusion     |
| run selector           | config panel top         | ~full x 36       | Completed training run       |
| dataset build selector | config panel             | ~full x 36       | Build to evaluate against   |
| run evaluation button  | pageHeader right side    | ~140 x 32        | Primary action               |
| metric cards           | results panel            | ~200 x 100 each  | mAP, precision, recall      |
| confusion matrix       | results panel            | remaining area   | Per-class matrix             |
| evaluation history     | subNav "History" tab     | full content     | Past evaluation records     |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, subNav dimensions match layout table
- [ ] Run selector shows only completed training runs
- [ ] Dataset build selector shows only completed builds
- [ ] Run button disabled when prerequisites not met
- [ ] Metric cards show formatted values with units
- [ ] Confusion matrix renders correctly (labels aligned)
- [ ] Evaluation History tab shows all past evaluations
- [ ] Empty state when no completed runs exist

---

### 8. Export Page (`/export`)

| Widget                   | Approx Position         | Expected Size    | Notes                         |
|--------------------------|-------------------------|------------------|-------------------------------|
| appBar                   | top edge                | 1920 x 56        |                               |
| primaryNav               | left edge               | 216 x 996        | "Export" item highlighted     |
| pageHeader               | main area top           | 1704 x 64        | "Export" + Export button      |
| subNav                   | below pageHeader        | 1704 x 48        | "Config / History"            |
| config panel (left)      | below subNav            | ~500 x remaining | Model selector, format        |
| model card (right side)  | right of config         | ~1156 x remaining | Model details, preview       |
| model selector           | config panel top        | ~full x 36       | Ready-to-export models        |
| export format dropdown   | config panel            | ~full x 36       | ONNX, TorchScript, etc.       |
| export path display      | config panel            | ~full x 36       | Output path preview           |
| export button            | pageHeader right side   | ~140 x 32        | Primary action                |
| model detail card        | model card area         | ~600 x 300       | Name, format, metrics, date   |
| model metrics table      | model card area         | ~full x 200      | Precision/recall by class     |
| export history           | subNav "History" tab    | full content     | Past export records           |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader, subNav dimensions match layout table
- [ ] Model selector shows only models with `ready = true`
- [ ] Model detail card updates when model is selected
- [ ] Export button disabled when no ready model
- [ ] Export progress bar shows during export
- [ ] Export History tab shows status of each export
- [ ] Empty state when no ready models exist

---

### 9. Config Page (`/config`)

| Widget                   | Approx Position         | Expected Size    | Notes                         |
|--------------------------|-------------------------|------------------|-------------------------------|
| appBar                   | top edge                | 1920 x 56        |                               |
| primaryNav               | left edge               | 216 x 996        | "Config" item highlighted     |
| pageHeader               | main area top           | 1704 x 64        | "Settings"                    |
| settings sidebar (left)  | below pageHeader        | ~240 x remaining | Category list                 |
| settings panel (right)   | right of sidebar        | ~1420 x remaining | Form fields per category     |
| category list            | settings sidebar        | ~240 x full      | General, Display, Export...   |
| each category item       | in list                 | ~240 x 36        | Icon + label                  |
| selected category        | highlighted in list     | ~240 x 36        | Active state indicator        |
| form fields              | settings panel          | form-dependent   | Typed inputs, toggles, paths  |
| reset defaults button    | pageHeader right side   | ~140 x 32        | Secondary action               |

**Acceptance:**
- [ ] appBar, primaryNav, pageHeader dimensions match layout table
- [ ] Settings sidebar (left) is ~240px; form panel fills remaining
- [ ] Category list scrolls independently
- [ ] Form fields show current values from config
- [ ] Changes persist across app restart
- [ ] Reset to defaults confirmation dialog
- [ ] Path fields show native file picker on click

---

## General Acceptance (All Pages)

- [ ] appBar is 56px tall and spans full width at top
- [ ] primaryNav is 216px wide (expanded) or 64px (collapsed)
- [ ] primaryNav items have hover and active states
- [ ] pageHeader is 64px tall with title and action buttons
- [ ] subNav (where present) is 48px tall with tab indicators
- [ ] statusBar is 28px tall at the very bottom
- [ ] No horizontal scrollbar at 1920px width
- [ ] Resizing below 1280px triggers responsive layout (nav collapses)
- [ ] Content area has 24px padding on all sides
- [ ] Cards in grids have 16px gap between them
- [ ] All text is visible (no truncation without ellipsis)
- [ ] Focus indicators visible on keyboard navigation
- [ ] Empty states show helpful illustration + message
- [ ] Loading states show skeleton or spinner
- [ ] Error states show message with retry action
