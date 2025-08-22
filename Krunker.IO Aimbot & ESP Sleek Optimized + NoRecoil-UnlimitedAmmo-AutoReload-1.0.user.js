// ==UserScript==
// @name         Krunker.IO Aimbot & ESP Sleek Optimized + NoRecoil/UnlimitedAmmo/AutoReload
// @version      1.0
// @description  Optimized Krunker aimbot & ESP with animated toggles, No Recoil, Infinite Ammo, AutoReload, and RMB hold aimbot
// @match        *://krunker.io/*
// @exclude      *://krunker.io/social*
// @exclude      *://krunker.io/editor*
// @grant        none
// @run-at       document-start
// @require      https://unpkg.com/three@0.150.0/build/three.min.js
// ==/UserScript==

const THREE = window.THREE; delete window.THREE;

// --- Settings ---
const settings = { aimbot: true, esp: true, espLines: true, wireframe: false };
const keyMap = { KeyB: 'aimbot', KeyM: 'esp', KeyN: 'espLines', KeyK: 'wireframe' };

// --- Scene & Input ---
let scene, rightMouseDown = false;

// --- Reusable THREE objects ---
const tempVec = new THREE.Vector3();
const tempObj = new THREE.Object3D(); tempObj.rotation.order = 'YXZ';
const geometry = new THREE.EdgesGeometry(new THREE.BoxGeometry(5, 15, 5).translate(0, 7.5, 0));
const material = new THREE.RawShaderMaterial({
    vertexShader: `attribute vec3 position; uniform mat4 projectionMatrix; uniform mat4 modelViewMatrix; void main(){ gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); gl_Position.z=1.0; }`,
    fragmentShader: `void main(){ gl_FragColor=vec4(1,0,0,1); }`
});
const line = new THREE.LineSegments(new THREE.BufferGeometry(), material);
line.frustumCulled = false;
const linePositions = new THREE.BufferAttribute(new Float32Array(100 * 2 * 3), 3);
line.geometry.setAttribute('position', linePositions);

// --- Hook scene ---
const originalPush = Array.prototype.push;
Array.prototype.push = function (...args) {
    try {
        const obj = args[0];
        if (obj?.parent?.type === 'Scene' && obj.parent.name === 'Main') {
            scene = obj.parent;
            Array.prototype.push = originalPush;
        }
    } catch {}
    return originalPush.apply(this, args);
};

// --- NoRecoil / UnlimitedAmmo / AutoReload classes ---
class NoRecoil { constructor(control, me) { this.me = me; this.control = control; this.enabled = false; } toggle() { this.enabled = !this.enabled; } onTick() { if (!this.enabled) return; this.me.recoilAnimYOld = this.me.recoilAnimY; this.me.recoilAnimY = 0; } }
class AutoReload { constructor(me, inputs) { this.me = me; this.inputs = inputs; this.enabled = true; } toggle() { this.enabled = !this.enabled; } onTick() { if (!this.enabled) return; if (this.me.ammos[this.me.weaponIndex] === 0) this.inputs[9] = 1; } }
class UnlimitedAmmo { constructor(me) { this.me = me; this.enabled = true; } toggle() { this.enabled = !this.enabled; } onTick() { if (!this.enabled) return; this.me.ammos[this.me.weaponIndex] = 101; } }

// --- Helpers ---
let noRecoilHelper, unlimitedAmmoHelper, autoReloadHelper;

// --- GUI ---
const gui = createGUI();
waitForBody(() => document.body.appendChild(gui));

function waitForBody(callback) {
    if (document.body) return callback();
    requestAnimationFrame(() => waitForBody(callback));
}

// --- Animate loop ---
function animate() {
    requestAnimationFrame(animate);
    if (!scene) return;

    let players = [], myPlayer = null, camera = null;

    for (const c of scene.children) {
        if (c.type !== 'Object3D') continue;
        const cam = c.children?.[0]?.children?.[0];
        if (cam?.type === 'PerspectiveCamera') { myPlayer = c; camera = cam; continue; }
        if (isPlayer(c) && !isTeammate(c, myPlayer)) players.push(c);
        if (c.material) c.material.wireframe = settings.wireframe;
    }
    if (!myPlayer || !camera) return;

    // Initialize helpers if not done yet
    if (!noRecoilHelper) {
        noRecoilHelper = new NoRecoil(myPlayer.control, myPlayer);
        unlimitedAmmoHelper = new UnlimitedAmmo(myPlayer);
        autoReloadHelper = new AutoReload(myPlayer, myPlayer.inputs);
        addHelperToggles(); // Add helper toggles dynamically
    }

    // Call helpers
    noRecoilHelper.onTick();
    unlimitedAmmoHelper.onTick();
    autoReloadHelper.onTick();

    let target, minScreenDist = Infinity, counter = 0;
    tempObj.matrix.copy(myPlayer.matrix).invert();

    for (const p of players) {
        if (!p.box) { const box = new THREE.LineSegments(geometry, material); box.frustumCulled = false; p.add(box); p.box = box; }
        if (p.position.x === myPlayer.position.x && p.position.z === myPlayer.position.z) { p.box.visible = false; if (line.parent !== p) p.add(line); continue; }

        tempVec.copy(p.position).add(new THREE.Vector3(0, 9, 0));
        tempVec.project(camera);
        const screenDist = Math.hypot(tempVec.x, tempVec.y);

        tempVec.copy(p.position).add(new THREE.Vector3(0, 9, 0)).applyMatrix4(tempObj.matrix);
        linePositions.setXYZ(counter++, 0, 10, -5);
        linePositions.setXYZ(counter++, tempVec.x, tempVec.y, tempVec.z);

        p.visible = settings.esp;
        p.box.visible = settings.esp;

        if (screenDist < minScreenDist && tempVec.z < 1) { target = p; minScreenDist = screenDist; }
    }

    linePositions.needsUpdate = true;
    line.geometry.setDrawRange(0, counter);
    line.visible = settings.espLines;

    // --- RMB aimbot (hold right mouse to aim)
    if (settings.aimbot && rightMouseDown && target) {
        tempVec.setScalar(0);
        target.children[0].children[0].localToWorld(tempVec);
        tempObj.position.copy(myPlayer.position);
        tempObj.lookAt(tempVec);
        myPlayer.children[0].rotation.x = -tempObj.rotation.x;
        myPlayer.rotation.y = tempObj.rotation.y + Math.PI;
    }
}

animate();

// --- Events ---
window.addEventListener('pointerdown', e => { if (e.button === 2) rightMouseDown = true; });
window.addEventListener('pointerup', e => { if (e.button === 2) rightMouseDown = false; });
window.addEventListener('keyup', e => {
    if (document.activeElement?.value !== undefined) return;
    if (keyMap[e.code]) toggleSetting(keyMap[e.code]);
    if (e.code === 'Slash') gui.style.display = gui.style.display === '' ? 'none' : '';
});

// --- Helper functions ---
function isPlayer(obj) { const hasModel = obj.children?.length > 0 && obj.children[0].type === 'Object3D'; const notEnvironment = !obj.name.includes('dog') && !obj.name.includes('cat'); return hasModel && notEnvironment; }
function isTeammate(obj, myPlayer) { for (const child of obj.children) { if (child.type === 'Sprite' || (child.type === 'Mesh' && child.material?.map)) return true; } if (!myPlayer || !obj.userData || !myPlayer.userData) return false; return obj.userData.isFriendly || (obj.userData.team && myPlayer.userData.team && obj.userData.team === myPlayer.userData.team); }
function toggleSetting(name) { settings[name] = !settings[name]; }

// --- GUI creation ---
function createGUI() {
    const guiEl = document.createElement('div');
    guiEl.innerHTML = `
    <style>
    .gui-panel{position:fixed;right:10px;top:10px;width:280px;background:rgba(0,0,0,0.8);border-radius:12px;padding:12px;font-family:monospace;color:#fff;box-shadow:0 0 15px rgba(0,0,0,0.5);z-index:999999;}
    .gui-header{font-weight:bold;font-size:16px;margin-bottom:10px;cursor:pointer;display:flex;justify-content:space-between;}
    .gui-content{display:flex;flex-direction:column;gap:8px;}
    .gui-item{display:flex;justify-content:space-between;align-items:center;background:#222;padding:6px 10px;border-radius:8px;cursor:pointer;transition:background 0.2s;}
    .gui-item:hover{background:#333;}
    .toggle{width:40px;height:20px;background:#555;border-radius:10px;position:relative;transition:background 0.2s;}
    .toggle-knob{width:18px;height:18px;background:#fff;border-radius:50%;position:absolute;top:1px;left:1px;transition:left 0.2s;}
    .on .toggle{background:lime;}
    .on .toggle-knob{left:21px;}
    </style>
    <div class="gui-panel">
        <div class="gui-header">Controls <span>[/]</span></div>
        <div class="gui-content"></div>
    </div>`;
    const content = guiEl.querySelector('.gui-content');

    // Original settings toggles
    for (const key in settings) {
        const item = document.createElement('div'); item.className = 'gui-item';
        const span = document.createElement('span'); span.innerText = key;
        const toggle = document.createElement('div'); toggle.className = 'toggle';
        const knob = document.createElement('div'); knob.className = 'toggle-knob'; toggle.appendChild(knob);
        if (settings[key]) item.classList.add('on');
        item.appendChild(span); item.appendChild(toggle);
        item.onclick = () => { settings[key] = !settings[key]; item.classList.toggle('on', settings[key]); };
        content.appendChild(item);
    }

    guiEl.querySelector('.gui-header').onclick = () => {
        const content = guiEl.querySelector('.gui-content');
        content.style.display = content.style.display === 'none' ? 'flex' : 'none';
    };
    return guiEl;
}

// --- Add helper toggles dynamically ---
function addHelperToggles() {
    const content = gui.querySelector('.gui-content');
    [['NoRecoilHelper', noRecoilHelper], ['UnlimitedAmmoHelper', unlimitedAmmoHelper], ['AutoReloadHelper', autoReloadHelper]].forEach(([name, helper]) => {
        const item = document.createElement('div');
        item.className = 'gui-item';
        const span = document.createElement('span');
        span.innerText = name.replace('Helper','');
        const toggle = document.createElement('div'); toggle.className = 'toggle';
        const knob = document.createElement('div'); knob.className = 'toggle-knob';
        toggle.appendChild(knob);
        item.appendChild(span); item.appendChild(toggle);
        item.onclick = () => { helper?.toggle(); item.classList.toggle('on'); };
        content.appendChild(item);
    });
}
