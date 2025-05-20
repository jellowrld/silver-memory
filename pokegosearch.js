// ==UserScript==
// @name         PokéGO Search Tool (Autocomplete + Coordinates + Click-to-Copy)
// @namespace    http://tampermonkey.net/
// @version      3.0
// @description  Search any Pokémon in GO from any site, see coordinates, and click to copy. Works via scraping PokéGO.me live data with autocomplete, cancel, and popup UI.
// @author       You
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @connect      pokego.me
// @connect      pogoapi.net
// ==/UserScript==

(function () {
    'use strict';

    let POKEMON_LIST = [];

    function loadPokemonNames() {
        GM_xmlhttpRequest({
            method: "GET",
            url: "https://pogoapi.net/api/v1/released_pokemon.json",
            onload: function (response) {
                const data = JSON.parse(response.responseText);
                POKEMON_LIST = Object.values(data).map(p => p.name).sort();
                console.log("Pokémon GO list loaded:", POKEMON_LIST.length);
            }
        });
    }

    function createSearchUI() {
        const container = document.createElement('div');
        container.id = 'poke-overlay';
        container.innerHTML = `
            <div id="poke-box">
                <input id="poke-search" type="text" placeholder="Search Pokémon..." autocomplete="off" />
                <button id="poke-cancel">Cancel</button>
                <div id="poke-suggestions"></div>
            </div>
        `;
        document.body.appendChild(container);

        const input = document.getElementById('poke-search');
        const suggestions = document.getElementById('poke-suggestions');

        input.addEventListener('input', () => {
            const val = input.value.toLowerCase();
            suggestions.innerHTML = '';
            if (!val) return;
            const matches = POKEMON_LIST.filter(name => name.toLowerCase().startsWith(val)).slice(0, 20);
            matches.forEach(name => {
                const div = document.createElement('div');
                div.textContent = name;
                div.className = 'poke-suggestion';
                div.onclick = () => {
                    input.value = name;
                    suggestions.innerHTML = '';
                    container.remove();
                    document.removeEventListener('click', outsideClick);
                    fetchCoordinates(name);
                };
                suggestions.appendChild(div);
            });
        });

        document.getElementById('poke-cancel').onclick = () => {
            container.remove();
            document.removeEventListener('click', outsideClick);
        };

        function outsideClick(e) {
            if (!document.getElementById('poke-box').contains(e.target)) {
                container.remove();
                document.removeEventListener('click', outsideClick);
            }
        }

        setTimeout(() => document.addEventListener('click', outsideClick), 100);
    }

    function fetchCoordinates(pokemonName) {
        const searchUrl = `https://pokego.me/coordinates?pokemon=${encodeURIComponent(pokemonName)}&city=All%20Locations`;

        GM_xmlhttpRequest({
            method: "GET",
            url: searchUrl,
            onload: function (response) {
                const parser = new DOMParser();
                const doc = parser.parseFromString(response.responseText, "text/html");
                const table = doc.querySelector("#coordinates-table");
                const rows = table?.querySelectorAll("tbody tr");

                if (!rows || rows.length === 0) {
                    alert(`No coordinates found for "${pokemonName}".`);
                    return;
                }

                const results = [];
                rows.forEach(row => {
                    const cols = row.querySelectorAll("td");
                    if (cols.length >= 5) {
                        results.push({
                            lat: cols[0].textContent.trim(),
                            lon: cols[1].textContent.trim(),
                            iv: cols[2].textContent.trim(),
                            lvl: cols[3].textContent.trim(),
                            cp: cols[4].textContent.trim()
                        });
                    }
                });

                if (results.length === 0) {
                    alert(`No valid entries found for "${pokemonName}".`);
                } else {
                    showResultsOverlay(pokemonName, results.slice(0, 30));
                }
            },
            onerror: () => alert("Failed to fetch data from PokéGO.me.")
        });
    }

    function showResultsOverlay(pokemonName, results) {
        const overlay = document.createElement('div');
        overlay.id = 'coords-overlay';

        const box = document.createElement('div');
        box.id = 'coords-box';

        const close = document.createElement('button');
        close.textContent = "Close";
        close.className = 'close-btn';
        close.onclick = () => overlay.remove();

        const title = document.createElement('h2');
        title.textContent = `Results for ${pokemonName}`;
        box.appendChild(close);
        box.appendChild(title);

        results.forEach(r => {
            const div = document.createElement('div');
            div.className = 'coord-entry';
            div.textContent = `(${r.lat}, ${r.lon}) - IV: ${r.iv}, Lvl: ${r.lvl}, CP: ${r.cp}`;
            div.onclick = () => {
                const coords = `${r.lat}, ${r.lon}`;
                navigator.clipboard.writeText(coords).then(() => {
                    div.style.backgroundColor = '#2a7';
                    div.textContent = `Copied: ${coords}`;
                    setTimeout(() => {
                        div.style.backgroundColor = '';
                        div.textContent = `(${r.lat}, ${r.lon}) - IV: ${r.iv}, Lvl: ${r.lvl}, CP: ${r.cp}`;
                    }, 1500);
                });
            };
            box.appendChild(div);
        });

        overlay.appendChild(box);
        document.body.appendChild(overlay);
    }

    function createTriggerButton() {
        const btn = document.createElement('button');
        btn.id = 'poke-trigger';
        btn.textContent = "PokéGO Search";
        btn.onclick = () => {
            if (!document.getElementById('poke-overlay')) {
                createSearchUI();
            }
        };
        document.body.appendChild(btn);
    }

    GM_addStyle(`
        #poke-trigger {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 100000;
            background: #0088cc;
            color: white;
            border: none;
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
        }
        #poke-box {
            background: #fff;
            padding: 10px;
            position: fixed;
            top: 100px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 100001;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            border-radius: 6px;
            width: 300px;
        }
        #poke-search {
            width: 100%;
            padding: 8px;
            font-size: 14px;
        }
        #poke-cancel {
            margin-top: 10px;
            padding: 5px 10px;
            background: #bbb;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        #poke-suggestions {
            max-height: 200px;
            overflow-y: auto;
            margin-top: 5px;
        }
        .poke-suggestion {
            padding: 6px;
            cursor: pointer;
            border-bottom: 1px solid #ccc;
        }
        .poke-suggestion:hover {
            background: #f0f0f0;
        }
        #coords-overlay {
            position: fixed;
            top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.6);
            z-index: 100002;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        #coords-box {
            background: #fff;
            color: #000;
            padding: 20px;
            border-radius: 10px;
            width: 80%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .close-btn {
            float: right;
            background: #c00;
            color: white;
            border: none;
            padding: 5px 10px;
            cursor: pointer;
            border-radius: 4px;
        }
        .coord-entry {
            padding: 6px;
            border-bottom: 1px solid #ddd;
            cursor: pointer;
        }
        .coord-entry:hover {
            background: #f0f0f0;
        }
    `);

    window.addEventListener('load', () => {
        loadPokemonNames();
        createTriggerButton();
    });
})();