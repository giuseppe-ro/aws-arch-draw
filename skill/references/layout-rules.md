# Layout & Spacing Rules

Extracted from `aws_arch_template.drawio`.

## Canvas / Page

| Property | Value |
|----------|-------|
| Grid | `grid="1" gridSize="10"` (always enabled, 10px) |
| Page size | `pageWidth="850" pageHeight="1100"` (portrait) |
| Background | `background="light-dark(#FFFFFF,#FFFFFF)"` (white) |
| Math / Shadow | `math="0" shadow="0"` (always) |

## Horizontal Spacing

| Rule | Value |
|------|-------|
| Icon size (all AWS) | **80 × 80 px** |
| Center-to-center between adjacent icons | **240 px** |
| Edge-to-edge gap between adjacent icons | **160 px** |
| First AWS icon X (after left external) | **240** |
| X grid formula | `x_n = 240 + (n × 240)` |

Grid positions: `240, 480, 720, 960, 1200, 1440, 1680, ...`

## Vertical Spacing

| Rule | Value |
|------|-------|
| Baseline row-to-row Y spacing | **240 px** (80px icon + 160px gap = 2× icon height) |
| First row Y | **160** |
| Row Y formula | `y_n = 160 + (n × 240)` |
| Within-row vertical offset (stacked icons, same X) | **160 px** |

Row grid: `160, 400, 640, 880, 1120, 1360, 1600, 1840, 2080, 2320, 2560, ...`

## Title Bar

| Property | Value |
|----------|-------|
| Position | `x=0, y=0` |
| Size | `width=1700, height=40` |
| Style | `text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;` |
| Font | `fontSize=18;fontStyle=1;fontColor=#232F3E;` |
| Value format | `<font style="font-size: 24px;">&lt;TITLE&gt;</font>` |

## Flow Direction

- **Left → Right** for each horizontal lane
- Multiple independent lanes stack **top → bottom**
- Each lane represents a separate pipeline / data flow
