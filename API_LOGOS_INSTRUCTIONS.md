# Instructions: Adding Real API Logos

## Overview
The API Marquee section on the landing page mockup has been updated to display real logo images instead of gradient placeholders.

## Location
Logo files should be placed in: `surfsense_web/public/api-logos/`

## Required Logo Files

Based on the images provided in PR comment #3904724532, please save the following files:

1. **scb-logo.png** - SCB (Statistiska centralbyrån) logo
2. **smhi-logo.png** - SMHI logo
3. **bolagsverket-logo.png** - Bolagsverket logo
4. **trafikverket-logo.png** - Trafikverket logo
5. **riksdagen-logo.png** - Riksdagen logo
6. **kolada-logo.png** - Kolada logo
7. **tavily-logo.png** - Tavily logo

## How to Add the Logos

### Step 1: Download the Images
The images were provided as GitHub asset URLs in the PR comment. Download each image.

### Step 2: Name and Save
Rename and save each downloaded image with the exact filename listed above in the `surfsense_web/public/api-logos/` directory.

### Step 3: Image Requirements
- **Format**: PNG (preferred) or SVG
- **Size**: Minimum 48x48px, recommended 64x64px or larger for better quality
- **Background**: Transparent background preferred for better integration
- **Filenames**: Must match exactly as listed above (case-sensitive)

## Current Implementation

The code has been updated in `surfsense_web/app/(home)/page-mockup/page.tsx`:

```typescript
const apis = [
  { name: "SCB", logo: "/api-logos/scb-logo.png" },
  { name: "SMHI", logo: "/api-logos/smhi-logo.png" },
  { name: "Bolagsverket", logo: "/api-logos/bolagsverket-logo.png" },
  { name: "Trafikverket", logo: "/api-logos/trafikverket-logo.png" },
  { name: "Riksdagen", logo: "/api-logos/riksdagen-logo.png" },
  { name: "Kolada", logo: "/api-logos/kolada-logo.png" },
  { name: "Tavily", logo: "/api-logos/tavily-logo.png" },
];
```

Each logo is displayed using Next.js Image component for optimal loading and performance.

## Temporary Placeholders

Temporary placeholder SVG files have been created in the logo directory. These will be replaced when you add the real logo images with the same filenames.

## Testing

After adding the real logos:
1. Navigate to `/page-mockup` route
2. Scroll to the API Marquee section
3. Verify all logos display correctly
4. Check hover effects and animations still work properly
5. Test in both light and dark modes

## Troubleshooting

If logos don't appear:
- Verify filenames match exactly (case-sensitive)
- Check that files are in `surfsense_web/public/api-logos/` directory
- Ensure file permissions are correct (readable)
- Clear Next.js cache: `rm -rf .next` and restart dev server
- Check browser console for image loading errors

