// Generates PWA icons from SVG using sharp
import sharp from "sharp";
import { writeFileSync } from "fs";

// Radar SVG scaled to fill a 512x512 canvas
// Background: #0B0D14 (dark), icon: #F59E0B (amber primary)
const makeSvg = (size, maskable = false) => {
  const bg = maskable
    ? `<rect width="${size}" height="${size}" fill="#0B0D14"/>`
    : `<rect width="${size}" height="${size}" rx="${Math.round(size * 0.22)}" fill="#0B0D14"/>`;

  // Icon fills 60% of canvas in safe zone (important for maskable)
  const iconSize = Math.round(size * 0.56);
  const offset = Math.round((size - iconSize) / 2);
  const scale = iconSize / 24;
  const sw = Math.max(1, (1.5 / scale).toFixed(3)); // stroke-width back-calculated

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  ${bg}
  <g transform="translate(${offset},${offset}) scale(${scale})" stroke="#F59E0B" stroke-width="${sw}" stroke-linecap="round" fill="none">
    <circle cx="12" cy="12" r="9"/>
    <circle cx="12" cy="12" r="5"/>
    <circle cx="12" cy="12" r="1.5" fill="#F59E0B" stroke="none"/>
    <line x1="12" y1="3" x2="12" y2="7"/>
    <line x1="12" y1="17" x2="12" y2="21"/>
    <line x1="3" y1="12" x2="7" y2="12"/>
    <line x1="17" y1="12" x2="21" y2="12"/>
  </g>
</svg>`;
};

const tasks = [
  { file: "public/icons/icon-192.png",        size: 192, maskable: false },
  { file: "public/icons/icon-512.png",        size: 512, maskable: false },
  { file: "public/icons/icon-maskable-192.png", size: 192, maskable: true },
  { file: "public/icons/icon-maskable-512.png", size: 512, maskable: true },
  { file: "public/icons/apple-touch-icon.png", size: 180, maskable: false },
  { file: "public/favicon.png",               size: 64,  maskable: false },
];

for (const { file, size, maskable } of tasks) {
  const svg = Buffer.from(makeSvg(size, maskable));
  await sharp(svg).png().toFile(file);
  console.log(`✓ ${file}`);
}

// Also write the SVG favicon
writeFileSync("public/favicon.svg", makeSvg(32, false));
console.log("✓ public/favicon.svg");
