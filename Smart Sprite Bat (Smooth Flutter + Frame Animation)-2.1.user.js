// ==UserScript==
// @name         Smart Sprite Bat (Smooth Flutter + Frame Animation)
// @namespace    http://tampermonkey.net/
// @version      2.1
// @description  Smooth animated bat that follows mouse cursor using sprite sheet and noise-based flutter
// @author       You
// @match        *://*/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // === Prevent Multiple Instances ===
    if (window.__smartBatInitialized) return;
    window.__smartBatInitialized = true;

    // === CONFIGURATION ===
    const SPRITE_URL = "https://i.postimg.cc/prBdLLfq/Rpg-Sprites-removebg-preview.png";
    const FRAME_WIDTH = 128, FRAME_HEIGHT = 128;
    const COLUMNS = 8, ROWS = 4;
    const TOTAL_FRAMES = COLUMNS * ROWS;
    const FRAME_DURATION = 100; // ms per frame

    // === Create Bat Element ===
    const bat = document.createElement("div");
    bat.id = "smart-bat";
    Object.assign(bat.style, {
        width: `${FRAME_WIDTH}px`,
        height: `${FRAME_HEIGHT}px`,
        position: "fixed",
        top: "100px",
        left: "100px",
        backgroundImage: `url('${SPRITE_URL}')`,
        backgroundSize: `${COLUMNS * FRAME_WIDTH}px ${ROWS * FRAME_HEIGHT}px`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "0px 0px",
        zIndex: 999999,
        pointerEvents: "none",
        imageRendering: "pixelated", // optional: "auto" for smooth, "pixelated" for crisp
        transition: "transform 0.2s ease-out",
    });
    document.body.appendChild(bat);

    // === Animate Sprite Frames ===
    let frame = 0, lastFrameTime = 0;
    function animateSprite(timestamp) {
        if (timestamp - lastFrameTime > FRAME_DURATION) {
            const col = frame % COLUMNS;
            const row = Math.floor(frame / COLUMNS);
            bat.style.backgroundPosition = `-${col * FRAME_WIDTH}px -${row * FRAME_HEIGHT}px`;
            frame = (frame + 1) % TOTAL_FRAMES;
            lastFrameTime = timestamp;
        }
        requestAnimationFrame(animateSprite);
    }

    // === Track Mouse + Flutter ===
    let mouseX = window.innerWidth / 2, mouseY = window.innerHeight / 2;
    let batX = mouseX, batY = mouseY;
    let flutterOffset = 0;
    document.addEventListener("mousemove", e => {
        mouseX = e.clientX;
        mouseY = e.clientY;
    });

    function updatePosition() {
        const dx = mouseX - batX;
        const dy = mouseY - batY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const speed = Math.min(12, Math.max(2, dist / 15)) * (1 + (Math.random() - 0.5) * 0.1);

        if (dist > 1) {
            batX += (dx / dist) * speed;
            batY += (dy / dist) * speed;
        }

        // Simulated flutter using offset sin waves
        flutterOffset += 0.05;
        const flutterX = Math.sin(flutterOffset * 2.3) * 6;
        const flutterY = Math.cos(flutterOffset * 3.7) * 6;

        const finalX = batX + flutterX;
        const finalY = batY + flutterY;
        bat.style.left = `${finalX}px`;
        bat.style.top = `${finalY}px`;

        // Smooth rotation based on movement direction
        const angle = Math.atan2(dy, dx) * (180 / Math.PI);
        bat.style.transform = `rotate(${angle}deg)`;

        requestAnimationFrame(updatePosition);
    }

    // === Launch Animation Loops ===
    requestAnimationFrame(animateSprite);
    requestAnimationFrame(updatePosition);
})();
