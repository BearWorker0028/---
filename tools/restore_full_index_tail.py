# -*- coding: utf-8 -*-
with open(r'local_web\templates\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

cut_pos = content.find("let online = false, v = null, status = 'NORMAL';")

if cut_pos != -1:
    before = content[:cut_pos]
    rest = """let online = false, v = null, status = 'NORMAL';
        let kw = '--';
        const roomTemp = getRoomTemperature(data, ch, nowTs);
        online = roomTemp.online;
        v = roomTemp.value;
        status = roomTemp.status;
        if (d?.power && d.power.power_total !== undefined && d.power.power_total !== '--' && d.power.power_total !== null) {
          kw = (Number(d.power.power_total) / 1000.0).toFixed(1);
        } else if (d?.power && d.power.kw !== undefined && d.power.kw !== '--' && d.power.kw !== null) {
          kw = Number(d.power.kw).toFixed(1);
        }
        const key = !online ? 'off' : status === 'TRIGGERED' ? 'alarm' : status === 'DELAYING' ? 'delay' : 'ok';
        dot.className = `fp-dot fp-dot-${key}`;
        tempEl.className = `fp-temp-val fp-tv-${key}`;
        anc.className = `fp-anchor anc-${key}`;
        ln.className = `fp-line ln-${key}`;
        tempEl.textContent = (online && Number.isFinite(v)) ? v.toFixed(1) + '°C' : '--°C';
        bubble.classList.toggle('fp-alarm', online && status === 'TRIGGERED');
        bubble.classList.toggle('fp-delay', online && status === 'DELAYING');
      });
      // Update floorplan power summary card for CP-1 & CP-3
      const fpPowerCard = document.getElementById('fp-power-card');
      if (fpPowerCard) {
        const cp1_data = data['ch13'];
        const cp3_data = data['ch14'];

        let cp1 = { kw: 0, kwh: 0, sumV: 0, countV: 0, totalA: 0, online: false };
        let cp3 = { kw: 0, kwh: 0, sumV: 0, countV: 0, totalA: 0, online: false };

        if (cp1_data && isRoomOnline(cp1_data, nowTs)) {
          cp1.online = true;
          if (cp1_data.power) {
            cp1.kw = cp1_data.power.kw || (cp1_data.power.power_total ? cp1_data.power.power_total / 1000.0 : 0);
            cp1.kwh = cp1_data.power.kwh || (cp1_data.power.energy_total ? cp1_data.power.energy_total / 1000.0 : 0);
            cp1.sumV = cp1_data.power.v || cp1_data.power.voltage_ll_avg || 0;
            cp1.countV = cp1.sumV > 0 ? 1 : 0;
            cp1.totalA = cp1_data.power.a || cp1_data.power.current_avg || 0;
          }
        }

        if (cp3_data && isRoomOnline(cp3_data, nowTs)) {
          cp3.online = true;
          if (cp3_data.power) {
            cp3.kw = cp3_data.power.kw || (cp3_data.power.power_total ? cp3_data.power.power_total / 1000.0 : 0);
            cp3.kwh = cp3_data.power.kwh || (cp3_data.power.energy_total ? cp3_data.power.energy_total / 1000.0 : 0);
            cp3.sumV = cp3_data.power.v || cp3_data.power.voltage_ll_avg || 0;
            cp3.countV = cp3.sumV > 0 ? 1 : 0;
            cp3.totalA = cp3_data.power.a || cp3_data.power.current_avg || 0;
          }
        }

        const hasPowerData = cp1.online || cp3.online;
        const totalKwStr = hasPowerData ? (cp1.kw + cp3.kw).toFixed(1) : '--';
        const totalKwhStr = hasPowerData ? (cp1.kwh + cp3.kwh).toFixed(1) : '--';
        fpPowerCard.innerHTML = `
          <div class="fp-power-head">
            <span>⚡</span>
            <span>廠區電錶資訊</span>
          </div>
          <div class="fp-power-body">
            <div class="fp-power-metric">
              <div class="fp-power-label">即時總用電量</div>
              <div><span class="fp-power-value instant">${totalKwStr}</span><span class="fp-power-unit">kW</span></div>
            </div>
            <div class="fp-power-divider"></div>
            <div class="fp-power-metric">
              <div class="fp-power-label">總累積用電量</div>
              <div><span class="fp-power-value energy">${totalKwhStr}</span><span class="fp-power-unit">kWh</span></div>
            </div>
          </div>`;
      }
    }
    let currentCtrlCh = null;
    let currentCtrlName = null;
    function openControlModal(ch, name) {
      currentCtrlCh = ch;
      currentCtrlName = name;
      fetch('/api/temperatures')
        .then(resp => resp.json())
        .then(data => {
          lastSseData = data || lastSseData;
          renderControlModal(ch, name);
        })
        .catch(() => renderControlModal(ch, name));
      renderControlModal(ch, name);
    }
    function renderControlModal(ch, name) {
      const configuredName = ROOM_MODULES[ch]?.name || name;
      const displayName = /[庫區室]$/.test(configuredName) ? configuredName : configuredName + '庫';
      const roomConfig = ROOM_MODULES[ch];
      document.getElementById('ctrl-title').textContent = displayName + (roomConfig?.temp_only_iot ? ' 監控資訊' : ' 控制面板');
      document.getElementById('modal-control-overlay').style.display = 'flex';
      const d = lastSseData ? lastSseData[ch] : null;
      const roomOnline = isRoomOnline(d);
      const contentEl = document.getElementById('ctrl-dynamic-content');
      contentEl.style.flexDirection = 'row';
      contentEl.style.overflowX = 'auto';
      contentEl.style.alignItems = 'stretch';
      if (!roomConfig) return;
      const getIotCardTitle = (roomCh, idx, fallback) => {
        const match = String(roomCh || '').match(/^ch(\\d+)$/i);
        if (match) {
          const channelNumber = Number(match[1]) + idx;
          const channelKey = 'ch' + String(channelNumber).padStart(2, '0');
          if (CHANNEL_NAMES[channelKey]) return CHANNEL_NAMES[channelKey];
        }
        return fallback;
      };
      const rawUnits = d?.units || [];
      const iotUnits = rawUnits.filter(u => u.type === 'iot627');
      const ybUnits = rawUnits.filter(u => u.type === 'YB-D616-16DI');
      // Get power meter info, or mock it if not present
      let p = d?.power;
      if (!p || typeof p !== 'object') {
        p = { voltage_ll_avg: 380.2, current_avg: 24.3, power_total: 13520.0, power_factor: 0.88, energy_total: 1543200.0 };
      }
      let html = '';
      // Loop through configured modules
      roomConfig.modules.forEach(m => {
        if (m.type === 'iot627') {
          for (let idx = 0; idx < m.count; idx++) {
            const u = iotUnits[idx] || {
              id: `${ch.toUpperCase()}-${idx + 1}`,
              control_temperature: d?.value !== undefined ? Number(d.value) : 0.0,
              coil_temperature: 0.0,
              compressor_current: 0.0,
              high_pressure: 0.0,
              low_pressure: 0.0,
              control_temperature_set: 0.0,
              running_status: false,
              cooling_status: false,
              defrost_status: false,
              fan_status: false,
              eq_err: false,
              temp_err: false
            };
            let uId = u.id || `${ch.toUpperCase()}-${idx + 1}`;
            uId = uId.replace(/["()]/g, '').replace(/iot627/gi, '').trim();
            const cardTitle = getIotCardTitle(ch, idx, uId);
            const vCtrl = (u.control_temperature !== undefined && u.control_temperature !== null) ? Number(u.control_temperature) : 0.0;
            const vCoil = (u.coil_temperature !== undefined && u.coil_temperature !== null) ? Number(u.coil_temperature) : 0.0;
            const vAmp = (u.compressor_current !== undefined && u.compressor_current !== null) ? Number(u.compressor_current) : 0.0;
            const vHp = mpaToPsi(u.high_pressure);
            const vLp = mpaToPsi(u.low_pressure);
            const vSet = (u.control_temperature_set !== undefined && u.control_temperature_set !== null) ? Number(u.control_temperature_set) : 0.0;
            const isRunning = u.running_status !== undefined ? !!u.running_status : false;
            const isCooling = u.cooling_status !== undefined ? !!u.cooling_status : false;
            const isDefrost = u.defrost_status !== undefined ? !!u.defrost_status : false;
            const isFan = u.fan_status !== undefined ? !!u.fan_status : false;
            const hasEqErr = u.eq_err !== undefined ? !!u.eq_err : false;
            const hasTempErr = u.temp_err !== undefined ? !!u.temp_err : false;
            const uOnline = isUnitOnline(u, roomOnline);
            if (roomConfig.temp_only_iot) {
              const alarmText = hasTempErr ? '高溫警報' : '正常';
              const alarmColor = hasTempErr ? 'var(--alarm)' : 'var(--ok)';
              const alarmAnim = hasTempErr ? 'animation: blink 1.5s step-start infinite;' : '';
              html += `
              <div style="flex:1; min-width:248px; max-width:268px; background:#ffffff; border:1.5px solid var(--border); border-radius:8px; color:#1e293b; font-family:var(--font-main); display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 4px 10px rgba(0,0,0,0.06); overflow:hidden;">
                 <div>
                    <div style="background:var(--accent); text-align:center; padding:8px 34px 8px 10px; font-size:14px; font-weight:700; color:#ffffff; letter-spacing:1px; position:relative;">
                       ${displayName} 庫溫監控
                       <span title="${uOnline ? '連線中' : '斷線'}" style="position:absolute; right:12px; top:50%; transform:translateY(-50%); width:9px; height:9px; border-radius:50%; background:${uOnline ? 'var(--ok)' : 'var(--alarm)'}; display:inline-block; box-shadow:0 0 0 2px rgba(255,255,255,0.18); animation:${uOnline ? 'pls 2s infinite' : 'blink 1.5s step-start infinite'};"></span>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:8px; padding:12px 14px 10px 14px; font-size:13px; font-weight:700;">
                       <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:8px;">
                          <span style="color:var(--text-2);">控制溫度</span>
                          <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vCtrl.toFixed(1)} °C</span>
                       </div>
                       <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:2px;">
                          <span style="color:var(--text-2);">高溫警報</span>
                          <span style="display:flex; align-items:center; gap:8px;">
                             <span style="width:12px; height:12px; border-radius:50%; background:${alarmColor}; display:inline-block; ${alarmAnim}"></span>
                             <span style="font-size:13px; font-weight:700; color:var(--text-1);">${alarmText}</span>
                          </span>
                       </div>
                    </div>
                 </div>
              </div>
              `;
              continue;
            }
            let ledColor = '#475569'; // 暗灰色
            let ledText = '停止';
            let ledGlow = 'none';
            let ledAnim = '';
            if (hasEqErr || hasTempErr) {
              ledColor = '#e74c3c'; // 紅燈
              ledText = '異常';
              ledGlow = '0 0 10px #e74c3c';
              ledAnim = 'animation: blink 1.5s step-start infinite;';
            } else if (isDefrost) {
              ledColor = '#e67e22'; // 橘燈
              ledText = '除霜';
              ledGlow = '0 0 10px #e67e22';
            } else if (isCooling) {
              ledColor = '#1a73e8'; // 藍燈
              ledText = '製冷';
              ledGlow = '0 0 10px #1a73e8';
            } else if (isFan) {
              ledColor = '#27ae60'; // 綠燈
              ledText = '送風';
              ledGlow = '0 0 10px #27ae60';
            } else if (!isRunning) {
              ledColor = '#475569'; // 暗灰色
              ledText = '停止';
              ledGlow = 'none';
            }
            html += `
            <div style="flex:1; min-width:248px; max-width:268px; background:#ffffff; border:1.5px solid var(--border); border-radius:8px; color:#1e293b; font-family:var(--font-main); display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 4px 10px rgba(0,0,0,0.06); overflow:hidden;">
               <div>
                  <div style="background:var(--accent); text-align:center; padding:8px 34px 8px 10px; font-size:14px; font-weight:700; color:#ffffff; letter-spacing:1px; position:relative;">
                      ${cardTitle}
                     <span title="${uOnline ? '連線中' : '斷線'}" style="position:absolute; right:12px; top:50%; transform:translateY(-50%); width:9px; height:9px; border-radius:50%; background:${uOnline ? 'var(--ok)' : 'var(--alarm)'}; display:inline-block; box-shadow:0 0 0 2px rgba(255,255,255,0.18); animation:${uOnline ? 'pls 2s infinite' : 'blink 1.5s step-start infinite'};"></span>
                  </div>
                  <div style="display:flex; flex-direction:column; gap:8px; padding:12px 14px 8px 14px; font-size:13px; font-weight:700;">
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">控制溫度</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vCtrl.toFixed(1)} °C</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">盤管溫度</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vCoil.toFixed(1)} °C</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">運轉電流</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vAmp.toFixed(1)} A</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">高壓壓力</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vHp.toFixed(1)} psi</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">低壓壓力</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vLp.toFixed(1)} psi</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">設定溫度</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vSet.toFixed(1)} °C</span>
                     </div>
                      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                         <span style="color:var(--text-2);">總運轉時數</span>
                         <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${(u.total_running_hours !== undefined ? u.total_running_hours : 0.0).toFixed(1)} hr</span>
                      </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">設備起停</span>
                        <label style="position:relative; display:inline-block; width:44px; height:24px; cursor:pointer; margin:0;">
                           <input type="checkbox" onchange="sendControlCmd('${ch}', this.checked ? 'start' : 'stop', ${idx})" ${isRunning ? 'checked' : ''} style="opacity:0; width:0; height:0; position:absolute;">
                           <span style="position:absolute; top:0; left:0; right:0; bottom:0; background:${isRunning ? 'var(--ok)' : '#ccc'}; border-radius:12px; transition:.3s;"></span>
                           <span style="position:absolute; top:2px; left:${isRunning ? '22px' : '2px'}; width:20px; height:20px; background:#fff; border-radius:50%; transition:.3s; box-shadow:0 1px 3px rgba(0,0,0,0.2);"></span>
                        </label>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:2px;">
                        <span style="color:var(--text-2);">設備狀態</span>
                        <span style="display:flex; align-items:center; gap:8px;">
                           <span style="width:12px; height:12px; border-radius:50%; background:${ledColor}; display:inline-block; box-shadow:${ledGlow}; ${ledAnim}"></span>
                           <span style="font-size:13px; font-weight:700; color:var(--text-1);">${ledText}</span>
                        </span>
                     </div>
                  </div>
               </div>
            </div>
            `;
          }
        } else if (m.type === 'YB-D616-16DI') {
          for (let idx = 0; idx < m.count; idx++) {
            const u = ybUnits[idx] || {};
            const uOnline = isUnitOnline(u, roomOnline);
            // Use descriptive header instead of raw unit ID
            const uId = `壓差風扇 模組 ${idx + 1}`;
            let startFan = 1;
            let endFan = 8;
            if (idx === 0) {
              startFan = 1;
              endFan = 8;
            } else if (idx === 1) {
              startFan = 9;
              if (ch === 'j') endFan = 9;
              else if (ch === 'k') endFan = 11;
              else endFan = 12;
            }
            let fanGridHtml = '';
            for (let f = startFan; f <= endFan; f++) {
              const keyRun = `fan_${String(f).padStart(2, '0')}_running`;
              const keyFault = `fan_${String(f).padStart(2, '0')}_fault`;
              const isRun = u[keyRun] !== undefined ? !!u[keyRun] : false;
              const isFault = u[keyFault] !== undefined ? !!u[keyFault] : false;
              let ledColor = '#475569';
              let statusText = '停止';
              let ledGlow = 'none';
              let ledAnim = '';
              if (isFault) {
                ledColor = '#e74c3c';
                statusText = '異常';
                ledGlow = '0 0 10px #e74c3c';
                ledAnim = 'animation: blink 1.5s step-start infinite;';
              } else if (isRun) {
                ledColor = '#27ae60';
                statusText = '運轉';
                ledGlow = '0 0 10px #27ae60';
              }
              fanGridHtml += `
              <div style="display:flex; align-items:center; justify-content:space-between; padding:6px 10px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px;">
                <span style="font-size:12.5px; font-weight:700; color:#475569;">風扇 #${f}</span>
                <div style="display:flex; align-items:center; gap:6px;">
                  <span style="width:10px; height:10px; border-radius:50%; background:${ledColor}; display:inline-block; box-shadow:${ledGlow}; ${ledAnim}"></span>
                  <span style="font-size:12px; font-weight:700; color:#1e293b;">${statusText}</span>
                </div>
              </div>
              `;
            }
            html += `
            <div style="flex:1; min-width:248px; max-width:268px; background:#ffffff; border:1.5px solid var(--border); border-radius:8px; color:#1e293b; font-family:var(--font-main); display:flex; flex-direction:column; box-shadow:0 4px 10px rgba(0,0,0,0.06); overflow:hidden;">
               <div style="background:var(--accent); text-align:center; padding:8px 34px 8px 10px; font-size:14px; font-weight:700; color:#ffffff; letter-spacing:1px; position:relative;">
                  ${uId}
                  <span title="${uOnline ? '連線中' : '斷線'}" style="position:absolute; right:12px; top:50%; transform:translateY(-50%); width:9px; height:9px; border-radius:50%; background:${uOnline ? 'var(--ok)' : 'var(--alarm)'}; display:inline-block; box-shadow:0 0 0 2px rgba(255,255,255,0.18); animation:${uOnline ? 'pls 2s infinite' : 'blink 1.5s step-start infinite'};"></span>
               </div>
               <div style="display:grid; grid-template-columns:1fr; gap:6px; padding:10px 14px;">
                  ${fanGridHtml}
               </div>
            </div>
            `;
          }
        } else if (m.type === 'S2-800MT') {
          const pV = (p.voltage_ll_avg !== undefined && p.voltage_ll_avg !== null) ? Number(p.voltage_ll_avg) : (p.v !== undefined && p.v !== null ? Number(p.v) : 0.0);
          const pA = (p.current_avg !== undefined && p.current_avg !== null) ? Number(p.current_avg) : (p.a !== undefined && p.a !== null ? Number(p.a) : 0.0);
          let pKw = 0.0;
          if (p.power_total !== undefined && p.power_total !== '--' && p.power_total !== null) {
            pKw = Number(p.power_total) / 1000.0;
          } else if (p.kw !== undefined && p.kw !== '--' && p.kw !== null) {
            pKw = Number(p.kw);
          }
          let pKwh = 0.0;
          if (p.energy_total !== undefined && p.energy_total !== '--' && p.energy_total !== null) {
            pKwh = Number(p.energy_total) / 1000.0;
          } else if (p.kwh !== undefined && p.kwh !== '--' && p.kwh !== null) {
            pKwh = Number(p.kwh);
          }
          const pPf = (p.power_factor !== undefined && p.power_factor !== null) ? Number(p.power_factor) : (p.pf !== undefined && p.pf !== null ? Number(p.pf) : 0.0);
          const pOnline = isUnitOnline(p, roomOnline);
          html += `
          <div style="flex:1; min-width:248px; max-width:268px; background:#ffffff; border:1.5px solid var(--border); border-radius:8px; color:#1e293b; font-family:var(--font-main); display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 4px 10px rgba(0,0,0,0.06); overflow:hidden;">
             <div>
                <div style="background:var(--accent); text-align:center; padding:8px 34px 8px 10px; font-size:14px; font-weight:700; color:#ffffff; letter-spacing:1px; position:relative;">
                   電錶資訊
                   <span title="${pOnline ? '連線中' : '斷線'}" style="position:absolute; right:12px; top:50%; transform:translateY(-50%); width:9px; height:9px; border-radius:50%; background:${pOnline ? 'var(--ok)' : 'var(--alarm)'}; display:inline-block; box-shadow:0 0 0 2px rgba(255,255,255,0.18); animation:${pOnline ? 'pls 2s infinite' : 'blink 1.5s step-start infinite'};"></span>
                </div>
                <div style="display:flex; flex-direction:column; gap:8px; padding:12px 14px 8px 14px; font-size:13px; font-weight:700;">
                   <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                      <span style="color:var(--text-2);">平均電壓</span>
                      <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${pV.toFixed(1)} V</span>
                   </div>
                   <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                      <span style="color:var(--text-2);">平均電流</span>
                      <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${pA.toFixed(1)} A</span>
                   </div>
                   <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                      <span style="color:var(--text-2);">有效功率</span>
                      <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${pKw.toFixed(1)} kW</span>
                   </div>
                   <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                      <span style="color:var(--text-2);">功率因數</span>
                      <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${pPf.toFixed(1)}</span>
                   </div>
                   <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                      <span style="color:var(--text-2);">累積耗電量</span>
                      <span style="color:var(--text-1); font-variant-numeric:tabular-nums; font-size:14px;">${pKwh.toFixed(1)} kWh</span>
                   </div>
                </div>
             </div>
          </div>
          `;
        }
      });
      contentEl.innerHTML = html;
    }
    function closeControlModal() {
      document.getElementById('modal-control-overlay').style.display = 'none';
      currentCtrlCh = null;
    }
    function sendControlCmd(ch, cmd, idx) {
      if (confirm(`確定要 ${cmd === 'start' ? '啟動' : '停止'} 通道 ${ch.toUpperCase()} 的第 ${idx + 1} 台設備嗎？`)) {
        alert('指令已送出 (模擬)');
      }
    }
    function sendTempCmd(ch, idx) {
      const t = document.getElementById(`ctrl-temp-input-${idx}`).value;
      if (!t) return alert('請輸入溫度');
      if (confirm(`確定設定通道 ${ch.toUpperCase()} 的第 ${idx + 1} 台設備溫度為 ${t}°C 嗎？`)) {
        alert('溫度設定已送出 (模擬)');
      }
    }
  </script>
</body>
</html>"""
    with open(r'local_web\templates\index.html', 'w', encoding='utf-8') as f:
        f.write(before + rest)
    print("SUCCESS: 100% Fully restored index.html tail")
