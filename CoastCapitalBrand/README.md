# CoastCapital Brand Kit

## What
Shared brand assets (CSS variables, SVG logo, fonts, color palette) consumed by every CoastCapital module's web UI. This is the single source of truth for the platform's visual identity.

## Why
Every module (Finance, HomeLab, PersonalAssistant, Sports, Database) has its own Flask web dashboard. Without a shared brand kit, each module drifts into its own design language. This folder ensures consistent typography, colors, and logo usage across the entire platform.

## How
Each module's `static/` folder symlinks or copies from this brand kit. The primary integration point is `brand.css`, which defines CSS custom properties that each module's own stylesheet consumes.

### Structure
```
CoastCapitalBrand/
  css/
    brand.css          <- CSS custom properties, base typography, shared classes
    nav.css            <- Platform navigation bar styles
  js/
    nav.js             <- Cross-module navigation component (auto-injected)
  img/
    logo.svg           <- Primary SVG logo (scalable)
    logo-icon.svg      <- Icon-only mark for compact spaces
    favicon.svg        <- Browser tab icon
  fonts/               <- Reserved for self-hosted fonts (currently CDN)
```

### Integration
In each module's base HTML template:
```html
<link rel="stylesheet" href="/static/brand/css/brand.css">
<link rel="stylesheet" href="/static/brand/css/nav.css">
<link rel="icon" href="/static/brand/img/favicon.svg">
<!-- At end of body: -->
<script src="/static/brand/js/nav.js"></script>
```

Add `data-cc-module` and `data-cc-page` attributes to the `<body>` tag:
```html
<body data-cc-module="finance" data-cc-page="dashboard">
```

### Platform Navigation
`nav.js` auto-injects a fixed navigation bar at the top of every page. It detects
the current module from `window.location.port` and resolves cross-module links using
`http://{hostname}:{port}{path}`. Works in both dev (localhost) and prod (macmini.local).

Module/port mapping: Finance (5000), Assistant (5100), HomeLab (5200), Sports (5300), Platform (5400), Database (8080), N8N (5678).

Each module mounts the brand folder into its static directory via Docker volume.
