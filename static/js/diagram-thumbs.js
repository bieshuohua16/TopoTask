/* Type-specific topology thumbnails shared by the library and project pages. */
(function () {
  const DEFS = `
<svg id="ttThumbDefs" width="0" height="0" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="ttLgIndigo" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#818cf8"/><stop offset="1" stop-color="#4f5bd5"/>
    </linearGradient>
    <filter id="ttSoft" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#1e293b" flood-opacity=".14"/>
    </filter>
    <filter id="ttSoftSm" x="-40%" y="-40%" width="180%" height="180%">
      <feDropShadow dx="0" dy="2" stdDeviation="2.4" flood-color="#1e293b" flood-opacity=".10"/>
    </filter>

    <!-- ================= 逻辑拓扑 ================= -->
    <g id="tt-thumb-logical">
      <circle cx="38" cy="120" r="62" fill="#6366f1" opacity=".07"/>
      <circle cx="288" cy="32" r="54" fill="#0d9488" opacity=".07"/>
      <circle cx="160" cy="78" r="47" fill="none" stroke="#c7d2fe" stroke-width="1.3" stroke-dasharray="4 5" opacity=".9"/>

      <g fill="none" stroke-linecap="round">
        <path d="M132 78 C108 78 92 64 70 64" stroke="#818cf8" stroke-width="2.2"/>
        <path d="M188 78 C214 78 232 54 258 54" stroke="#818cf8" stroke-width="2.2"/>
        <path d="M146 106 C136 122 98 120 74 118" stroke="#5eead4" stroke-width="2.2"/>
        <path d="M188 98 C218 104 236 114 250 116" stroke="#5eead4" stroke-width="2.2"/>
      </g>

      <g filter="url(#ttSoftSm)">
        <circle cx="70" cy="64" r="15" fill="#fff" stroke="#a5b4fc" stroke-width="1.6"/>
        <circle cx="258" cy="54" r="15" fill="#fff" stroke="#99f6e4" stroke-width="1.6"/>
        <circle cx="74" cy="118" r="14" fill="#fff" stroke="#a5b4fc" stroke-width="1.6"/>
        <circle cx="250" cy="116" r="14" fill="#fff" stroke="#99f6e4" stroke-width="1.6"/>
      </g>

      <g fill="none" stroke="#4f5bd5" stroke-width="1.5" stroke-linecap="round">
        <circle cx="70" cy="64" r="5.4"/>
        <path d="M70 58.6v-3M70 72.4v-3M64.6 64h-3M78.4 64h-3"/>
        <rect x="68.5" y="112.5" width="11" height="10" rx="2"/>
        <path d="M71 116h6M71 119.5h6"/>
      </g>
      <path d="M246 60c-2.5 0-4.5-2-4.5-4.5 0-2.3 1.7-4.2 4-4.5.7-3 3.3-5 6.4-5 2.8 0 5.2 1.7 6.1 4.2.5-.2 1-.3 1.6-.3 2.9 0 5.3 2.4 5.3 5.3s-2.4 5.3-5.3 5.3H246z" fill="#e6f7f4" stroke="#0d9488" stroke-width="1.4"/>
      <g stroke="#0d9488" stroke-width="1.5" fill="#fff">
        <ellipse cx="250" cy="112" rx="6" ry="2.6"/>
        <path d="M244 112v7c0 1.4 2.7 2.6 6 2.6s6-1.2 6-2.6v-7"/>
      </g>

      <g filter="url(#ttSoft)">
        <rect x="132" y="50" width="56" height="56" rx="15" fill="url(#ttLgIndigo)" stroke="#c7d2fe" stroke-width="1.5"/>
        <rect x="146" y="64" width="28" height="28" rx="7" fill="#fff" opacity=".16"/>
        <g stroke="#fff" stroke-width="2" stroke-linecap="round" fill="none">
          <path d="M155 72h12M151 79h16M155 86h12"/>
          <circle cx="150" cy="72" r="1.6" fill="#fff" stroke="none"/>
          <circle cx="170" cy="79" r="1.6" fill="#fff" stroke="none"/>
          <circle cx="150" cy="86" r="1.6" fill="#fff" stroke="none"/>
        </g>
      </g>

      <g fill="#fff" stroke="#6366f1" stroke-width="1.4">
        <circle cx="118" cy="78" r="2.6"/><circle cx="202" cy="80" r="2.6"/>
        <circle cx="110" cy="112" r="2.6"/><circle cx="216" cy="104" r="2.6"/>
      </g>
    </g>

    <!-- ================= 系统架构 ================= -->
    <g id="tt-thumb-architecture">
      <circle cx="42" cy="112" r="58" fill="#8b5cf6" opacity=".06"/>
      <circle cx="286" cy="32" r="54" fill="#4f5bd5" opacity=".06"/>

      <line x1="54" y1="30" x2="54" y2="126" stroke="#ddd6fe" stroke-width="1.3" stroke-dasharray="3 4"/>
      <g fill="#a78bfa">
        <circle cx="54" cy="34" r="2.4"/><circle cx="54" cy="78" r="2.4"/><circle cx="54" cy="122" r="2.4"/>
      </g>

      <g filter="url(#ttSoftSm)">
        <circle cx="34" cy="62" r="9" fill="#f3edff" stroke="#c4b5fd" stroke-width="1.4"/>
        <path d="M25 79c1.2-6.5 16.6-6.5 18 0" fill="#f3edff" stroke="#c4b5fd" stroke-width="1.4"/>
      </g>
      <path d="M43 70h17" stroke="#c4b5fd" stroke-width="1.3" stroke-dasharray="3 3"/>

      <g filter="url(#ttSoft)">
        <rect x="68" y="26" width="226" height="27" rx="9" fill="#fff" stroke="#c7d2fe" stroke-width="1.3"/>
        <rect x="68" y="64" width="226" height="27" rx="9" fill="#fff" stroke="#ddd6fe" stroke-width="1.3"/>
        <rect x="68" y="102" width="226" height="27" rx="9" fill="#fff" stroke="#99f6e4" stroke-width="1.3"/>
      </g>

      <g>
        <rect x="76" y="32" width="4" height="15" rx="2" fill="#6366f1"/>
        <rect x="76" y="70" width="4" height="15" rx="2" fill="#8b5cf6"/>
        <rect x="76" y="108" width="4" height="15" rx="2" fill="#14b8a6"/>
      </g>

      <g fill="#eef0ff" stroke="#a5b4fc" stroke-width="1.1">
        <rect x="88" y="33" width="38" height="13" rx="4"/>
        <rect x="132" y="33" width="38" height="13" rx="4"/>
        <rect x="176" y="33" width="38" height="13" rx="4"/>
      </g>
      <g fill="#f3edff" stroke="#c4b5fd" stroke-width="1.1">
        <rect x="88" y="71" width="54" height="13" rx="4"/>
        <rect x="148" y="71" width="54" height="13" rx="4"/>
        <rect x="208" y="71" width="54" height="13" rx="4"/>
      </g>
      <g fill="#e6f7f4" stroke="#5eead4" stroke-width="1.1">
        <rect x="88" y="109" width="58" height="13" rx="4"/>
        <rect x="152" y="109" width="58" height="13" rx="4"/>
      </g>
      <g stroke="#0d9488" stroke-width="1.4" fill="#fff">
        <ellipse cx="246" cy="111" rx="14" ry="4"/>
        <path d="M232 111v10c0 2.2 6.3 4 14 4s14-1.8 14-4v-10"/>
        <path d="M232 116c0 2.2 6.3 4 14 4s14-1.8 14-4" fill="none"/>
      </g>

      <g fill="#8b5cf6">
        <path d="M124 53v6" stroke="#8b5cf6" stroke-width="1.5"/>
        <polygon points="124,64 120,57.5 128,57.5"/>
        <path d="M228 53v6" stroke="#8b5cf6" stroke-width="1.5"/>
        <polygon points="228,64 224,57.5 232,57.5"/>
        <path d="M124 91v6" stroke="#8b5cf6" stroke-width="1.5"/>
        <polygon points="124,102 120,95.5 128,95.5"/>
      </g>

      <g fill="none" stroke="#a5b4fc" stroke-width="1.2">
        <path d="M104 39.5h6M146 39.5h6M190 39.5h6"/>
      </g>
      <g fill="#8b5cf6" opacity=".55">
        <circle cx="118" cy="39.5" r="1.4"/><circle cx="160" cy="39.5" r="1.4"/><circle cx="204" cy="39.5" r="1.4"/>
      </g>
    </g>

    <!-- ================= 部署图 ================= -->
    <g id="tt-thumb-deployment">
      <circle cx="40" cy="36" r="56" fill="#14b8a6" opacity=".07"/>
      <circle cx="286" cy="116" r="58" fill="#f59e0b" opacity=".06"/>

      <rect x="24" y="24" width="272" height="112" rx="14" fill="#0d9488" opacity=".035"/>
      <rect x="24" y="24" width="272" height="112" rx="14" fill="none" stroke="#5eead4" stroke-width="1.4" stroke-dasharray="6 5"/>

      <g filter="url(#ttSoftSm)">
        <path d="M54 54c-4.5 0-8-3.4-8-7.5 0-4 3.2-7.3 7.2-7.5.8-3.8 4.2-6.5 8.1-6.5 3.7 0 6.9 2.4 8 5.8.6-.2 1.3-.3 2-.3 3.9 0 7.1 3.1 7.1 7s-3.2 7-7.1 7H54z" fill="#fff" stroke="#14b8a6" stroke-width="1.6"/>
      </g>

      <g filter="url(#ttSoftSm)">
        <rect x="132" y="34" width="58" height="20" rx="6" fill="#fff" stroke="#f59e0b" stroke-width="1.4"/>
        <circle cx="143" cy="44" r="2.5" fill="#f59e0b"/>
        <path d="M151 44h27" stroke="#f59e0b" stroke-width="1.6" stroke-linecap="round"/>
      </g>

      <g fill="none" stroke-linecap="round">
        <path d="M86 46h46" stroke="#5eead4" stroke-width="1.5" stroke-dasharray="3 3"/>
        <path d="M161 54v9" stroke="#5eead4" stroke-width="1.5"/>
        <path d="M88 63h144" stroke="#5eead4" stroke-width="1.5"/>
        <path d="M88 63v9M161 63v9M232 63v9" stroke="#5eead4" stroke-width="1.5"/>
      </g>

      <g filter="url(#ttSoft)">
        <rect x="64" y="72" width="48" height="52" rx="7" fill="#fff" stroke="#99f6e4" stroke-width="1.4"/>
        <rect x="136" y="72" width="48" height="52" rx="7" fill="#fff" stroke="#99f6e4" stroke-width="1.4"/>
        <rect x="208" y="72" width="48" height="52" rx="7" fill="#fff" stroke="#99f6e4" stroke-width="1.4"/>
      </g>

      <g fill="#f8fafc" stroke="#e2e8f0" stroke-width="1">
        <rect x="71" y="79" width="34" height="8" rx="2"/><rect x="71" y="90" width="34" height="8" rx="2"/>
        <rect x="71" y="101" width="34" height="8" rx="2"/><rect x="71" y="112" width="34" height="6" rx="2"/>
        <rect x="143" y="79" width="34" height="8" rx="2"/><rect x="143" y="90" width="34" height="8" rx="2"/>
        <rect x="143" y="101" width="34" height="8" rx="2"/><rect x="143" y="112" width="34" height="6" rx="2"/>
        <rect x="215" y="79" width="34" height="8" rx="2"/><rect x="215" y="90" width="34" height="8" rx="2"/>
        <rect x="215" y="101" width="34" height="8" rx="2"/><rect x="215" y="112" width="34" height="6" rx="2"/>
      </g>
      <g>
        <circle cx="106" cy="83" r="1.8" fill="#14b8a6"/><circle cx="106" cy="94" r="1.8" fill="#14b8a6"/>
        <circle cx="106" cy="105" r="1.8" fill="#f59e0b"/>
        <circle cx="178" cy="83" r="1.8" fill="#14b8a6"/><circle cx="178" cy="94" r="1.8" fill="#14b8a6"/>
        <circle cx="178" cy="105" r="1.8" fill="#14b8a6"/>
        <circle cx="250" cy="83" r="1.8" fill="#14b8a6"/><circle cx="250" cy="94" r="1.8" fill="#f59e0b"/>
        <circle cx="250" cy="105" r="1.8" fill="#14b8a6"/>
      </g>

      <g fill="#d97706">
        <path d="M270 42l-7 11h5l-2 8 7-11h-5z" opacity=".9"/>
      </g>
      <path d="M44 126h232" stroke="#99f6e4" stroke-width="1.2" stroke-dasharray="2 5" opacity=".8"/>
    </g>

    <!-- ================= 其他 ================= -->
    <g id="tt-thumb-other">
      <circle cx="44" cy="116" r="58" fill="#64748b" opacity=".05"/>
      <circle cx="286" cy="30" r="54" fill="#f59e0b" opacity=".06"/>

      <g transform="rotate(4 160 78)" opacity=".75">
        <rect x="84" y="28" width="142" height="102" rx="10" fill="#fff" stroke="#e2e8f0" stroke-width="1.2"/>
      </g>
      <g transform="rotate(-2.5 160 78)" filter="url(#ttSoft)">
        <rect x="86" y="22" width="146" height="106" rx="10" fill="#fff" stroke="#cbd5e1" stroke-width="1.3"/>
        <path d="M214 22h18v18" fill="#f8fafc" stroke="#d4dbe8" stroke-width="1.2"/>
        <path d="M214 22l18 18" stroke="#e2e8f0" stroke-width="1.1"/>
      </g>

      <g transform="rotate(-2.5 160 78)">
        <g fill="none" stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="3 3">
          <path d="M124 54h36M181 64l-20 13M151 90l-20-23"/>
        </g>
        <circle cx="118" cy="54" r="7" fill="#eef0ff" stroke="#6366f1" stroke-width="1.5"/>
        <circle cx="118" cy="54" r="2" fill="#6366f1"/>
        <rect x="168" y="43" width="30" height="18" rx="5" fill="#f3edff" stroke="#8b5cf6" stroke-width="1.5"/>
        <path d="M174 49h18M174 54h12" stroke="#a78bfa" stroke-width="1.2" stroke-linecap="round"/>
        <path d="M151 92l9-15 9 15z" fill="#e6f7f4" stroke="#0d9488" stroke-width="1.5"/>
        <g stroke="#cbd5e1" stroke-width="1" opacity=".8">
          <path d="M100 34h10M100 38h6"/>
        </g>
      </g>

      <g transform="rotate(6 230 112)" filter="url(#ttSoftSm)">
        <rect x="209" y="96" width="40" height="28" rx="4" fill="#fff4e5" stroke="#f6dfbf" stroke-width="1.2"/>
        <g fill="#d97706">
          <circle cx="220" cy="110" r="1.8"/><circle cx="228" cy="110" r="1.8"/><circle cx="236" cy="110" r="1.8"/>
        </g>
      </g>
    </g>
  </defs>
</svg>`;

  const IDS = {
    topology: 'tt-thumb-logical',
    architecture: 'tt-thumb-architecture',
    deployment: 'tt-thumb-deployment',
    other: 'tt-thumb-other'
  };

  function ensureDefs() {
    if (document.getElementById('ttThumbDefs')) return;
    document.body.insertAdjacentHTML('beforeend', DEFS);
  }

  function forKind(kind) {
    ensureDefs();
    const id = IDS[kind] || IDS.other;
    return `<svg class="thumb-art" viewBox="0 0 320 150" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false"><use href="#${id}"></use></svg>`;
  }

  window.TTDiagramThumbs = { forKind, ensureDefs, IDS };
})();
