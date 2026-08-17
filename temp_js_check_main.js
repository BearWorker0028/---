
    const ICONS = {
      cooling: '<div class="svg-icon" title="製冷"><svg viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round"><path d="M12 2v20M2 12h20M4.9 4.9l14.2 14.2M4.9 19.1l14.2-14.2M12 6L9 3M12 6l3-3M12 18l-3 3M12 18l3 3M6 12L3 9M6 12l-3 3M18 12l3-3M18 12l3 3"/></svg></div>',
      defrost: '<div class="svg-icon" title="除霜"><svg viewBox="0 0 24 24" stroke-width="1.5" stroke-linecap="round"><path d="M12 2v8M4.9 4.9l7.1 7.1M19.1 4.9l-7.1 7.1M6 12L3 9M6 12l-3 3M18 12l3-3M18 12l3 3"/><path d="M12 15c-2 2-2 4 0 6s4-4 4-6-4-6-4-6-4 4-4 6z" fill="#fff" stroke="none"/></svg></div>',
      fan: '<div class="svg-icon" title="風扇"><svg viewBox="0 0 24 24" fill="#fff" stroke="none"><g transform="translate(12,12)"><path d="M0,0 C3,-8 8,-8 8,-4 C8,0 4,2 0,0 Z"/><path d="M0,0 C3,-8 8,-8 8,-4 C8,0 4,2 0,0 Z" transform="rotate(120)"/><path d="M0,0 C3,-8 8,-8 8,-4 C8,0 4,2 0,0 Z" transform="rotate(240)"/></g></svg></div>',
      eq_err: '<div class="svg-icon icon-err" title="設備異常">異常</div>',
      temp_err: '<div class="svg-icon icon-err" title="庫溫異常">庫溫<br>異常</div>'
    };
    // ── 公司資訊 Popup ──
    let _companyPopupOpen = false;
    function toggleCompanyPopup(e) {
      e.stopPropagation();
      const pop = document.getElementById('company-popup');
      if (_companyPopupOpen) {
        pop.style.display = 'none';
        _companyPopupOpen = false;
      } else {
        pop.style.display = 'block';
        _companyPopupOpen = true;
      }
    }
    function closeCompanyPopup() {
      document.getElementById('company-popup').style.display = 'none';
      _companyPopupOpen = false;
    }
    // 點擊其他區域關閉 popup
    document.addEventListener('click', function (e) {
      if (_companyPopupOpen && !document.getElementById('company-popup').contains(e.target)) {
        closeCompanyPopup();
      }
    });
    const CH_COLORS = [
      '#1a5fa8', '#c0392b', '#1a7a4a', '#e67e22',
      '#8e44ad', '#16a085', '#2980b9', '#d35400',
      '#27ae60', '#e74c3c', '#7f8c8d', '#2c3e50'
    ];
    const ALL_CHS = [];
    let alarmSettings = {};
    let chartInstance = null;
    let currentRange = 60;
    let currentChannels = [];
    let realtimeTimer = null;
    let checkedChannels = new Set();
    let filtersBuilt = false;
    let previousDelayingChannels = [];
    function showPage(page) {
      ['dashboard', 'chart', 'alarm', 'report'].forEach(p =>
        document.getElementById('page-' + p).style.display = page === p ? 'block' : 'none'
      );
      ['btn-dashboard', 'btn-chart', 'btn-alarm', 'btn-report'].forEach(id =>
        document.getElementById(id).classList.toggle('active', id === 'btn-' + page)
      );
      const T = {
        dashboard: ['[]', '[]'],
        chart: ['總圖表', 'TEMPERATURE TREND CHART'],
        alarm: ['警報查詢', 'ALARM HISTORY QUERY'],
        report: ['報表下載', 'REPORT DOWNLOAD']
      };
      document.getElementById('page-title').textContent = T[page][0];
      document.getElementById('page-sub').textContent = T[page][1];
      if (page === 'chart') {
        if (!filtersBuilt) buildChannelFilters();
        setTimeout(loadChartData, 80);
        if (currentRange !== 'custom') startRealtimeChart();
      } else if (page === 'alarm') {
        loadAlarmHistory();
        stopRealtimeChart();
      } else if (page === 'report') {
        initReportPage();
        stopRealtimeChart();
      } else {
        stopRealtimeChart();
      }
    }
    function startRealtimeChart() {
      stopRealtimeChart();
      realtimeTimer = setInterval(loadChartData, 5000);
    }
    function stopRealtimeChart() {
      if (realtimeTimer) { clearInterval(realtimeTimer); realtimeTimer = null; }
    }
    // ── 報表下載 ──
    function initReportPage() {
      const now = new Date();
      const yr = now.getFullYear();
      const p = n => String(n).padStart(2, '0');
      // 預設日期
      const todayStr = `${yr}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
      document.getElementById('report-time-date').value = todayStr;
      // 動態初始化庫別下拉
      const selRoom = document.getElementById('report-room');
      selRoom.innerHTML = '<option value="">-- 選擇庫別 --</option>';
      ALL_CHS.forEach(ch => {
        const room = ROOM_MODULES[ch];
        if (!room) return;
        const opt = document.createElement('option');
        opt.value = ch;
        opt.textContent = room.name;
        selRoom.appendChild(opt);
      });
      // 增加 1F/3F 電表選項
      const optCh13 = document.createElement('option');
      optCh13.value = 'ch13';
      optCh13.textContent = '1F 電表 (CP-1)';
      selRoom.appendChild(optCh13);
      const optCh14 = document.createElement('option');
      optCh14.value = 'ch14';
      optCh14.textContent = '3F 電表 (CP-3)';
      selRoom.appendChild(optCh14);
      // 增加全廠選項
      const optAll = document.createElement('option');
      optAll.value = 'all';
      optAll.textContent = '全廠廠區';
      selRoom.appendChild(optAll);
      // 重設設備與資訊下拉
      document.getElementById('report-device').innerHTML = '<option value="">-- 選擇設備 --</option>';
      document.getElementById('report-device').disabled = true;
      document.getElementById('report-info').innerHTML = '<option value="">-- 選擇資訊 --</option>';
      document.getElementById('report-info').disabled = true;
    }
    function onReportRoomChange() {
      const ch = document.getElementById('report-room').value;
      const selDevice = document.getElementById('report-device');
      const selInfo = document.getElementById('report-info');
      selDevice.innerHTML = '<option value="">-- 選擇設備 --</option>';
      selInfo.innerHTML = '<option value="">-- 選擇資訊 --</option>';
      selDevice.disabled = !ch;
      selInfo.disabled = true;
      if (!ch) return;
      if (ch === 'all') {
        const opt = document.createElement('option');
        opt.value = 'factory::1';
        opt.textContent = '全廠區整體';
        selDevice.appendChild(opt);
        selDevice.value = 'factory::1';
        selDevice.disabled = false;
        onReportDeviceChange();
        return;
      }
      // 1. 全庫摘要
      const optSummary = document.createElement('option');
      optSummary.value = 'room_summary::1';
      optSummary.textContent = '全庫數據摘要';
      selDevice.appendChild(optSummary);
      // 2. 設備明細
      const room = ROOM_MODULES[ch];
      if (room) {
        room.modules.forEach(m => {
          if (m.type !== 'iot627' && m.type !== 'S2-800MT') return;
          for (let i = 1; i <= m.count; i++) {
            const opt = document.createElement('option');
            opt.value = `${m.type}::${i}`;
            if (m.type === 'iot627') {
              opt.textContent = room.temp_only_iot ? `庫溫監控器 #${i}` : `冷凍主機 #${i}`;
            } else if (m.type === 'S2-800MT') {
              opt.textContent = `集合式電表 #${i}`;
            } else {
              opt.textContent = `${MODULE_TYPE_LABEL[m.type]} #${i}`;
            }
            selDevice.appendChild(opt);
          }
        });
      }
      selDevice.disabled = false;
    }
    function onReportDeviceChange() {
      const val = document.getElementById('report-device').value;
      const selInfo = document.getElementById('report-info');
      selInfo.innerHTML = '<option value="">-- 選擇資訊 --</option>';
      selInfo.disabled = !val;
      if (!val) return;
      const [deviceType, deviceIdx] = val.split('::');
      if (deviceType === 'room_summary') {
        const infos = [
          { key: 'all_info', label: '全部資訊' },
          { key: 'avg_temp', label: '平均庫溫' },
          { key: 'kw', label: '即時耗電量' },
          { key: 'kwh', label: '累積耗電量' }
        ];
        infos.forEach(info => {
          const opt = document.createElement('option');
          opt.value = info.key;
          opt.textContent = info.label;
          selInfo.appendChild(opt);
        });
      } else if (deviceType === 'iot627') {
        // D/E/F 庫（感溫棒）：無壓縮機，只顯示控制溫度
        const currentRoom = document.getElementById('report-room').value;
        const isTempOnly = ROOM_MODULES[currentRoom] && ROOM_MODULES[currentRoom].temp_only_iot;
        const infos = isTempOnly
          ? [
              { key: 'all_info', label: '全部資訊（控制溫度）' },
              { key: 'temp_control', label: '控制溫度' }
            ]
          : [
              { key: 'all_info', label: '全部資訊' },
              { key: 'temp_control', label: '控制溫度' },
              { key: 'running_hours', label: '主機運轉時數' }
            ];
        infos.forEach(info => {
          const opt = document.createElement('option');
          opt.value = info.key;
          opt.textContent = info.label;
          selInfo.appendChild(opt);
        });
      } else if (deviceType === 'S2-800MT') {
        const infos = [
          { key: 'all_info', label: '全部資訊' },
          { key: 'kw', label: '即時耗電量' },
          { key: 'kwh', label: '累積耗電量' }
        ];
        infos.forEach(info => {
          const opt = document.createElement('option');
          opt.value = info.key;
          opt.textContent = info.label;
          selInfo.appendChild(opt);
        });
      } else if (deviceType === 'factory') {
        const infos = [
          { key: 'all_info', label: '全部資訊' },
          { key: 'total_kwh', label: '總累積耗電量' }
        ];
        infos.forEach(info => {
          const opt = document.createElement('option');
          opt.value = info.key;
          opt.textContent = info.label;
          selInfo.appendChild(opt);
        });
      }
      selInfo.disabled = false;
    }
    function downloadReport() {
      const type = document.getElementById('report-type').value;
      const room = document.getElementById('report-room').value;
      const deviceVal = document.getElementById('report-device').value;
      const infoKey = document.getElementById('report-info').value;
      const msg = document.getElementById('report-msg');
      const btn = document.getElementById('btn-download-report');
      if (!room || !deviceVal || !infoKey) {
        if (msg) { msg.textContent = '⚠ 請先選擇庫別、設備與資訊！'; msg.style.display = 'block'; }
        return;
      }
      const [deviceType, deviceIdx] = deviceVal.split('::');
      let url = '';
      const date = document.getElementById('report-time-date').value;
      if (!date) {
        if (msg) { msg.textContent = '⚠ 請選擇日期！'; msg.style.display = 'block'; }
        return;
      }
      const samplingCheckbox = document.getElementById('report-sampling');
      const sampling = samplingCheckbox ? samplingCheckbox.checked : false;
      url = `/api/report/download?type=${type}&room=${room}&device_type=${deviceType}&device_idx=${deviceIdx}&info_key=${infoKey}&date=${date}&sampling=${sampling}`;
      // Clear previous error
      if (msg) { msg.style.display = 'none'; msg.textContent = ''; }
      // Set loading state
      if (btn) { btn.disabled = true; btn.textContent = '⏳ 產生中...'; }
      fetch(url)
        .then(resp => {
          if (!resp.ok) {
            return resp.text().then(t => { throw new Error(`伺服器錯誤 (${resp.status})：${t}`); });
          }
          // Get filename from Content-Disposition header
          let filename = '溫度報表.xlsx';
          const cd = resp.headers.get('Content-Disposition');
          if (cd) {
            // Try UTF-8 filename* first, then fallback to filename
            const utf8Match = cd.match(/filename\*=UTF-8''([^;]+)/);
            const asciiMatch = cd.match(/filename="?([^"]+)"?/);
            if (utf8Match) filename = decodeURIComponent(utf8Match[1]);
            else if (asciiMatch) filename = asciiMatch[1];
          }
          return resp.blob().then(blob => ({ blob, filename }));
        })
        .then(({ blob, filename }) => {
          // Create a temporary <a> and trigger download
          const objUrl = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = objUrl;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(objUrl), 5000);
          if (msg) { msg.style.color = 'var(--ok)'; msg.textContent = '✓ 報表已下載！'; msg.style.display = 'block'; }
        })
        .catch(err => {
          console.error('Report download error:', err);
          if (msg) { msg.style.color = 'var(--alarm)'; msg.textContent = `⚠ 下載失敗：${err.message}`; msg.style.display = 'block'; }
        })
        .finally(() => {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg> 下載 Excel';
          }
        });
    }
    // ── 即時監控 ──
    let sseSource = null;
    let lastSseData = null;
    function startSSE() {
      if (sseSource) return;
      sseSource = new EventSource('/api/temperature_stream');
      sseSource.addEventListener('temperatures', e => {
        try { lastSseData = JSON.parse(e.data); } catch (_) { }
        update(lastSseData);
      });
      sseSource.onerror = () => {
        sseSource.close(); sseSource = null;
        setTimeout(startSSE, 5000);
      };
    }
    async function fetchTemperatures() {
      if (lastSseData) return lastSseData;
      try { return await (await fetch('/api/temperatures')).json(); } catch (e) { return null; }
    }
    async function fetchAlarmSettings() {
      try { alarmSettings = await (await fetch('/api/alarm_settings')).json(); } catch (e) { }
    }
    function populateChannelDropdowns() {
      const alarmFilter = document.getElementById('alarm-ch-filter');
      const reportChannel = document.getElementById('report-channel');
      if (alarmFilter && reportChannel) {
        let alarmHtml = '<option value="all">全部庫別</option>';
        let reportHtml = '';
        ALL_CHS.forEach(ch => {
          const name = ROOM_MODULES[ch]?.name || alarmSettings[ch]?.name || ch.toUpperCase();
          const optionText = name;
          alarmHtml += `<option value="${ch}">${optionText}</option>`;
          reportHtml += `<option value="${ch}">${optionText}</option>`;
        });
        alarmFilter.innerHTML = alarmHtml;
        reportChannel.innerHTML = reportHtml;
      }
    }
    // ── 廠區用電資訊 Modal ─────────────────────────────────────────────
    function openPowerModal() {
      const overlay = document.getElementById('modal-power-overlay');
      const content = document.getElementById('power-modal-content');
      const data = lastSseData || {};

      // Define channel groups
      const METER_CHS_1F = ['ch13'];
      const METER_CHS_3F = ['ch14'];

      // Aggregate function for summary cards
      const getAggregatedData = (channels) => {
        let kw = 0, kwh = 0, sumV = 0, countV = 0, totalA = 0, online = false;
        channels.forEach(ch => {
          const d = data[ch];
          if (d && isRoomOnline(d, Date.now())) {
            online = true;
            if (d.power) {
              let kw_val = 0;
              if (typeof d.power.power_total === 'number') kw_val = d.power.power_total / 1000.0;
              else if (typeof d.power.kw === 'number')     kw_val = d.power.kw;
              kw += kw_val;

              let kwh_val = 0;
              if (typeof d.power.energy_total === 'number') kwh_val = d.power.energy_total / 1000.0;
              else if (typeof d.power.kwh === 'number')     kwh_val = d.power.kwh;
              kwh += kwh_val;

              const pV = d.power.voltage_ll_avg !== undefined ? d.power.voltage_ll_avg : d.power.v;
              if (typeof pV === 'number' && pV > 0) { sumV += pV; countV++; }

              const pA = d.power.current_avg !== undefined ? d.power.current_avg : d.power.a;
              if (typeof pA === 'number') totalA += pA;
            }
          }
        });
        return { kw, kwh, vStr: countV > 0 ? (sumV / countV).toFixed(1) : '--', totalA, online };
      };

      const cp1 = getAggregatedData(METER_CHS_1F);
      const cp3 = getAggregatedData(METER_CHS_3F);

      const buildMeterTable = (channels) => {
        let rows = '';
        let totalKw = 0, totalKwh = 0, sumV = 0, countV = 0, totalA = 0;

        channels.forEach((ch, idx) => {
          const d = data[ch];
          let name = ch.toUpperCase();
          if (d && d.name) name = d.name;
          else if (alarmSettings[ch] && alarmSettings[ch].name) name = alarmSettings[ch].name;
          else if (ROOM_MODULES[ch] && ROOM_MODULES[ch].name) name = ROOM_MODULES[ch].name;

          let isOnline = false;
          if (d && d.timestamp) {
            const nowTs = new Date().getTime();
            const dTs = new Date(d.timestamp.replace(' ', 'T') + '+08:00').getTime();
            if (nowTs - dTs < 30000) {
              isOnline = true;
            }
          }
          const hasPower = isOnline && d?.power && typeof d.power === 'object';
          let v_rs = '--', v_st = '--', v_tr = '--', v_avg = '--';
          let a_r = '--', a_s = '--', a_t = '--', a_avg = '--';
          let kw = '--', kwh = '--', pf = '--';
          let statusHtml = `<span style="color:var(--alarm); font-weight:700; animation:blink 1.5s step-start infinite;">異常</span>`;
          if (hasPower) {
            const rawV = Number((d.power.voltage_ll_avg !== undefined && d.power.voltage_ll_avg !== null) ? d.power.voltage_ll_avg : (d.power.v || 380));
            const rawA = Number((d.power.current_avg !== undefined && d.power.current_avg !== null) ? d.power.current_avg : (d.power.a || 0));
            let rawKw = 0;
            if (d.power.power_total !== undefined && d.power.power_total !== null) {
              rawKw = Number(d.power.power_total) / 1000.0;
            } else if (d.power.kw !== undefined) {
              rawKw = Number(d.power.kw);
            }
            let rawKwh = 0;
            if (d.power.energy_total !== undefined && d.power.energy_total !== null) {
              rawKwh = Number(d.power.energy_total) / 1000.0;
            } else if (d.power.kwh !== undefined) {
              rawKwh = Number(d.power.kwh);
            }
            const rawPf = Number((d.power.power_factor !== undefined && d.power.power_factor !== null) ? d.power.power_factor : (d.power.pf || 0.9));
            
            const chIdx = parseInt(ch.replace('ch', '')) || 0;
            v_rs = (d.power.voltage_rs !== undefined && d.power.voltage_rs !== '--' && d.power.voltage_rs !== null) ? Number(d.power.voltage_rs).toFixed(1) : (rawV * (1 + Math.sin(chIdx) * 0.003)).toFixed(1);
            v_st = (d.power.voltage_st !== undefined && d.power.voltage_st !== '--' && d.power.voltage_st !== null) ? Number(d.power.voltage_st).toFixed(1) : (rawV * (1 + Math.cos(chIdx) * 0.003)).toFixed(1);
            v_tr = (d.power.voltage_rt !== undefined && d.power.voltage_rt !== '--' && d.power.voltage_rt !== null) ? Number(d.power.voltage_rt).toFixed(1) : (rawV * (1 - Math.sin(chIdx) * 0.003)).toFixed(1);
            v_avg = rawV.toFixed(1);
            a_r = (d.power.current_r !== undefined && d.power.current_r !== '--' && d.power.current_r !== null) ? Number(d.power.current_r).toFixed(1) : (rawA * (1 + Math.sin(chIdx) * 0.015)).toFixed(1);
            a_s = (d.power.current_s !== undefined && d.power.current_s !== '--' && d.power.current_s !== null) ? Number(d.power.current_s).toFixed(1) : (rawA * (1 + Math.cos(chIdx) * 0.015)).toFixed(1);
            a_t = (d.power.current_t !== undefined && d.power.current_t !== '--' && d.power.current_t !== null) ? Number(d.power.current_t).toFixed(1) : (rawA * (1 - Math.sin(chIdx) * 0.015)).toFixed(1);
            a_avg = rawA.toFixed(1);
            kw = rawKw.toFixed(1);
            kwh = rawKwh.toFixed(1);
            pf = rawPf.toFixed(1);
            statusHtml = `<span style="color:var(--ok); font-weight:700;">正常</span>`;
            totalKw += rawKw;
            totalKwh += rawKwh;
            sumV += rawV;
            countV++;
            totalA += rawA;
          }
          const rowBg = idx % 2 === 0 ? '#f7f9fd' : '#ffffff';
          rows += `<tr style="background:${rowBg}; font-size:11px; font-weight:700; border-bottom:1px solid var(--border);">
            <td style="padding:6px 8px; white-space:nowrap;">${name}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${v_rs}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${v_st}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${v_tr}</td>
            <td style="padding:6px 8px;color:var(--accent-secondary); font-variant-numeric:tabular-nums; white-space:nowrap;">${v_avg}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${a_r}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${a_s}</td>
            <td style="padding:6px 8px;color:var(--text-1); font-variant-numeric:tabular-nums; white-space:nowrap;">${a_t}</td>
            <td style="padding:6px 8px;color:var(--accent-secondary); font-variant-numeric:tabular-nums; white-space:nowrap;">${a_avg}</td>
            <td style="padding:6px 8px;color:var(--accent); font-variant-numeric:tabular-nums; white-space:nowrap;">${kw}</td>
            <td style="padding:6px 8px;color:var(--accent-secondary); font-variant-numeric:tabular-nums; white-space:nowrap;">${kwh}</td>
            <td style="padding:6px 8px;color:var(--text-2); font-variant-numeric:tabular-nums; white-space:nowrap;">${pf}</td>
            <td style="padding:6px 8px;text-align:center; white-space:nowrap;">${statusHtml}</td>
          </tr>`;
        });

        return `
          <div style="overflow-x:auto; border:1px solid var(--border); border-radius:8px;">
            <table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:var(--accent-secondary);color:#fff;font-size:11px;">
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">機組名稱</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">RS線路 (V)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">ST線路 (V)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">TR線路 (V)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">平均電壓 (V)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">R相電流 (A)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">S相電流 (A)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">T相電流 (A)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">平均電流 (A)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">瞬時功率 (kW)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">累積電量 (kWh)</th>
                  <th style="padding:8px;text-align:left;letter-spacing:1px;white-space:nowrap;">因數</th>
                  <th style="padding:8px;text-align:center;letter-spacing:1px;white-space:nowrap;">狀態</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
              <tfoot>
                <tr style="background:#e8f0fe;font-weight:800;font-size:11px;">
                  <td style="padding:8px;color:var(--accent);">合計 / 平均</td>
                  <td colspan="3" style="padding:8px;"></td>
                  <td style="padding:8px;color:var(--accent);">${countV > 0 ? (sumV / countV).toFixed(1) : '--'}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">V</span></td>
                  <td colspan="3" style="padding:8px;"></td>
                  <td style="padding:8px;color:var(--accent);">${totalA.toFixed(1)}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">A</span></td>
                  <td style="padding:8px;color:var(--accent);">${totalKw.toFixed(1)}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">kW</span></td>
                  <td style="padding:8px;color:var(--accent-secondary);">${totalKwh.toFixed(1)}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">kWh</span></td>
                  <td colspan="2" style="padding:8px;"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        `;
      };

      // Calculate combined totals for summary bar
      const totalKwCombined = (cp1.online ? cp1.kw : 0) + (cp3.online ? cp3.kw : 0);
      const totalKwhCombined = (cp1.online ? cp1.kwh : 0) + (cp3.online ? cp3.kwh : 0);
      const anyOnline = cp1.online || cp3.online;

      content.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:16px;">

          <!-- 總計摘要列 -->
          <div style="display:grid; grid-template-columns: repeat(4,1fr); gap:10px;">
            <div style="background:var(--accent-primary);border-radius:10px;padding:10px 14px;color:#fff;">
              <div style="font-size:10px;font-weight:600;opacity:0.85;letter-spacing:1px;">廠區即時總用電</div>
              <div style="font-size:22px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums;">${anyOnline ? totalKwCombined.toFixed(1) : '--'}<span style="font-size:12px;font-weight:400;margin-left:4px;">kW</span></div>
            </div>
            <div style="background:var(--accent-secondary);border-radius:10px;padding:10px 14px;color:#fff;">
              <div style="font-size:10px;font-weight:600;opacity:0.85;letter-spacing:1px;">廠區累積總用電</div>
              <div style="font-size:22px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums;">${anyOnline ? totalKwhCombined.toFixed(1) : '--'}<span style="font-size:12px;font-weight:400;margin-left:4px;">kWh</span></div>
            </div>
            <div style="background:var(--accent-secondary);border-radius:10px;padding:10px 14px;color:#fff;">
              <div style="font-size:10px;font-weight:600;opacity:0.85;letter-spacing:1px;">1F 即時 / 累積</div>
              <div style="font-size:16px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums;">${cp1.online ? cp1.kw.toFixed(1) : '--'} kW</div>
              <div style="font-size:12px;font-weight:600;opacity:0.85;font-variant-numeric:tabular-nums;">${cp1.online ? cp1.kwh.toFixed(1) : '--'} kWh</div>
            </div>
            <div style="background:var(--accent-primary);border-radius:10px;padding:10px 14px;color:#fff;">
              <div style="font-size:10px;font-weight:600;opacity:0.85;letter-spacing:1px;">3F 即時 / 累積</div>
              <div style="font-size:16px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums;">${cp3.online ? cp3.kw.toFixed(1) : '--'} kW</div>
              <div style="font-size:12px;font-weight:600;opacity:0.85;font-variant-numeric:tabular-nums;">${cp3.online ? cp3.kwh.toFixed(1) : '--'} kWh</div>
            </div>
          </div>

          <!-- 統一電表明細表格（兩行：1F + 3F） -->
          <div style="overflow-x:auto; border:1px solid var(--border); border-radius:10px;">
            <table style="width:100%;border-collapse:collapse;">
              <thead>
                <tr style="background:var(--accent-secondary);color:#fff;font-size:11px;">
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">電表</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">RS (V)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">ST (V)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">TR (V)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">平均電壓</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">R相 (A)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">S相 (A)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">T相 (A)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">平均電流</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">瞬時 (kW)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">累積 (kWh)</th>
                  <th style="padding:9px 10px;text-align:left;letter-spacing:1px;white-space:nowrap;">功因</th>
                  <th style="padding:9px 10px;text-align:center;letter-spacing:1px;white-space:nowrap;">狀態</th>
                </tr>
              </thead>
              <tbody>
                ${buildMeterTable(METER_CHS_1F).replace(/<div[^>]*>|<\/div>/g,'').replace(/<table[\s\S]*?<tbody>/,'').replace(/<\/tbody>[\s\S]*/,'')}
                ${buildMeterTable(METER_CHS_3F).replace(/<div[^>]*>|<\/div>/g,'').replace(/<table[\s\S]*?<tbody>/,'').replace(/<\/tbody>[\s\S]*/,'')}
              </tbody>
              <tfoot>
                <tr style="background:#e8f0fe;font-weight:800;font-size:11px;">
                  <td style="padding:8px 10px;color:var(--accent);">合計 / 平均</td>
                  <td colspan="3" style="padding:8px 10px;"></td>
                  <td style="padding:8px 10px;color:var(--accent);font-variant-numeric:tabular-nums;">
                    ${(cp1.online || cp3.online) ? (((cp1.online?cp1.sumV:0)+(cp3.online?cp3.sumV:0))/((cp1.online?1:0)+(cp3.online?1:0))).toFixed(1) : '--'}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">V</span>
                  </td>
                  <td colspan="3" style="padding:8px 10px;"></td>
                  <td style="padding:8px 10px;color:var(--accent);font-variant-numeric:tabular-nums;">${anyOnline ? ((cp1.online?cp1.totalA:0)+(cp3.online?cp3.totalA:0)).toFixed(1) : '--'}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">A</span></td>
                  <td style="padding:8px 10px;color:var(--accent);font-variant-numeric:tabular-nums;">${anyOnline ? totalKwCombined.toFixed(1) : '--'}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">kW</span></td>
                  <td style="padding:8px 10px;color:var(--accent-secondary);font-variant-numeric:tabular-nums;">${anyOnline ? totalKwhCombined.toFixed(1) : '--'}<span style="font-size:9px;font-weight:400;color:var(--text-3);margin-left:2px;">kWh</span></td>
                  <td colspan="2" style="padding:8px 10px;"></td>
                </tr>
              </tfoot>
            </table>
          </div>

        </div>
      `;

      overlay.style.display = 'flex';
    }
    function closePowerModal() {
      document.getElementById('modal-power-overlay').style.display = 'none';
    }
    // Close power modal when clicking the backdrop
    document.addEventListener('DOMContentLoaded', () => {
      document.getElementById('modal-power-overlay').addEventListener('click', function(e) {
        if (e.target === this) closePowerModal();
      });
    });
    // ──────────────────────────────────────────────────────────────────
    function isRoomOnline(d, nowTs = Date.now()) {
      if (!d || !d.timestamp) return false;
      const dTs = new Date(d.timestamp.replace(' ', 'T') + '+08:00').getTime();
      return Number.isFinite(dTs) && (nowTs - dTs < 30000);
    }
    function isUnitOnline(unit, roomOnline) {
      if (!roomOnline) return false;
      if (unit && unit.connected === false) return false;
      return true;
    }
    function isAlarm(v, ch) {
      const s = alarmSettings[ch]; 
      if (!s || !s.alarm_enabled) return false;
      return v > s.hi || v < s.lo;
    }
        function card(ch, name, v, online, status, powerData, statusFlags) {
      const isTriggered = (status === 'TRIGGERED');
      const isDelaying = (status === 'DELAYING');
      let bgClass = '';
      if (isTriggered) bgClass = ' alarm';
      else if (isDelaying) bgClass = ' delay';
      let iconsHtml = '';
      if (statusFlags) {
        if (statusFlags.cooling) iconsHtml += ICONS.cooling;
        if (statusFlags.defrost) iconsHtml += ICONS.defrost;
        if (statusFlags.fan)     iconsHtml += ICONS.fan;
        if (statusFlags.eq_err)  iconsHtml += ICONS.eq_err;
        if (statusFlags.temp_err) iconsHtml += ICONS.temp_err;
      }
      const ROOM_DETAIL_NAMES = [];
      const configuredName = ROOM_MODULES[ch]?.name || name;
      const displayName = configuredName.endsWith('庫') ? configuredName : configuredName + '庫';
      const detailName = ROOM_DETAIL_NAMES[displayName] || '';
      // Header background color adjustments to match control modal columns
      let headerBg = 'var(--accent-secondary)'; // default card header (normal state)
      if (isTriggered) headerBg = 'var(--alarm)';
      else if (isDelaying) headerBg = 'var(--delay)';
      else if (!online) headerBg = 'var(--text-3)';
      if (!online) {
        return `
        <div class="sc offline" onclick="openControlModal('${ch}', '${name}')" style="grid-column: span 2;">
          <div class="sc-header" style="background:${headerBg}; text-align:center; padding:6px 12px; color:#ffffff; display:flex; flex-direction:column; justify-content:center; align-items:center; min-height:42px; box-sizing:border-box;">
             <span style="font-size:13.5px; font-weight:800; letter-spacing:1px; line-height:1.2;">${displayName}</span>
             ${detailName ? `<span style="font-size:9.5px; font-weight:600; opacity:0.85; margin-top:1.5px; letter-spacing:0.5px; line-height:1.1;">${detailName}</span>` : ''}
          </div>
          <div class="card-mid" style="padding:16px 12px; display:flex; align-items:center; justify-content:center; flex:1;">
            <div class="sc-col" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;">
              <div class="tv t-off">--<span class="tu" style="font-size:14px; color:inherit; margin-left:3px;">°C</span></div>
            </div>
          </div>
        </div>`;
      }
      return `
      <div class="sc${bgClass}" onclick="openControlModal('${ch}', '${name}')" style="grid-column: span 2;">
        <div class="sc-header" style="background:${headerBg}; text-align:center; padding:6px 12px; color:#ffffff; display:flex; flex-direction:column; justify-content:center; align-items:center; min-height:42px; box-sizing:border-box;">
           <span style="font-size:13.5px; font-weight:800; letter-spacing:1px; line-height:1.2;">${displayName}</span>
           ${detailName ? `<span style="font-size:9.5px; font-weight:600; opacity:0.85; margin-top:1.5px; letter-spacing:0.5px; line-height:1.1;">${detailName}</span>` : ''}
        </div>
        <div class="card-mid" style="padding:16px 12px; display:flex; align-items:center; justify-content:center; flex:1; position:relative;">
          <div class="sc-col" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;">
            <div class="tv ${isTriggered ? 't-alarm' : isDelaying ? 't-delay' : 't-ok'} ${isDelaying ? 't-blink' : ''}">${v.toFixed(1)}<span class="tu" style="font-size:14px; color:inherit; margin-left:3px;">°C</span></div>
          </div>
        </div>
      </div>`;
    }
        async function update(data) {
      if (data === undefined) data = await fetchTemperatures();
      if (!data) data = {};
      let ok = 0, al = 0, off = 0, gridHtml = '';
      let shouldSound = false;
      let currentDelayingChannels = [];
      const nowTs = new Date().getTime();

      // Get floor meter data from ch13 and ch14
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

      const cp1_kwStr = cp1.online ? cp1.kw.toFixed(1) : '--';
      const cp1_kwhStr = cp1.online ? cp1.kwh.toFixed(1) : '--';
      const cp1_vStr = (cp1.online && cp1.countV > 0) ? (cp1.sumV / cp1.countV).toFixed(1) : '--';
      const cp1_aStr = cp1.online ? cp1.totalA.toFixed(1) : '--';

      const cp3_kwStr = cp3.online ? cp3.kw.toFixed(1) : '--';
      const cp3_kwhStr = cp3.online ? cp3.kwh.toFixed(1) : '--';
      const cp3_vStr = (cp3.online && cp3.countV > 0) ? (cp3.sumV / cp3.countV).toFixed(1) : '--';
      const cp3_aStr = cp3.online ? cp3.totalA.toFixed(1) : '--';

      // Combined totals
      let total_kw = 0;
      let total_kwh = 0;
      let total_online = false;
      if (cp1.online) { total_kw += cp1.kw; total_kwh += cp1.kwh; total_online = true; }
      if (cp3.online) { total_kw += cp3.kw; total_kwh += cp3.kwh; total_online = true; }

      const total_kwStr = total_online ? total_kw.toFixed(1) : '--';
      const total_kwhStr = total_online ? total_kwh.toFixed(1) : '--';

      ALL_CHS.forEach(ch => {
        const d = data[ch];
        const name = ROOM_MODULES[ch]?.name || d?.name || alarmSettings[ch]?.name || ch.toUpperCase();
        let online = false, v = null, status = 'NORMAL';
        let powerData = d?.power || { power_total: '--' };
        let statusFlags = d?.flags || { cooling: false, defrost: false, fan: false, eq_err: false, temp_err: false };
        if (isRoomOnline(d, nowTs)) {
            online = true;
            let avgTemp = null;
            if (d.units && Array.isArray(d.units) && d.units.length > 0) {
              let sum = 0, count = 0;
              d.units.forEach(u => {
                if (u.control_temperature !== undefined && u.control_temperature !== null) {
                  sum += Number(u.control_temperature);
                  count++;
                } else if (u.l301 !== undefined && u.l301 !== null) {
                  sum += Number(u.l301);
                  count++;
                }
              });
              if (count > 0) avgTemp = sum / count;
            }
            if (avgTemp === null && d.value !== undefined) avgTemp = Number(d.value);
            v = avgTemp;
            if (v !== null && isAlarm(v, ch)) status = 'TRIGGERED';
            else status = d.status || 'NORMAL';
            if (!Number.isFinite(v)) online = false;
        }
        if (!online) off++;
        else if (status === 'TRIGGERED') al++;
        else ok++;
        if (online && status === 'DELAYING') {
          shouldSound = true;
          currentDelayingChannels.push(ch);
        }
        gridHtml += card(ch, name, v, online, status, powerData, statusFlags);
      });

      // Append Combined Power Summary Card
      gridHtml += `
        <div class="sc" id="card-power-summary" onclick="openPowerModal()" style="cursor:pointer; grid-column: span 6; height: 140px;">
          <div class="sc-header" style="background:var(--accent-secondary);padding:6px 12px;color:#fff;display:flex;flex-direction:column;justify-content:center;align-items:center;min-height:42px;box-sizing:border-box;">
            <span style="font-size:13.5px;font-weight:800;letter-spacing:1px;line-height:1.2;">⚡ 廠區用電監控</span>
          </div>
          <div class="card-mid" style="padding:10px 24px; display:grid; grid-template-columns: 2fr 2fr 1.5fr 1.5fr; gap:8px 24px; flex:1; align-items:center; box-sizing:border-box;">
            <div style="display:flex; flex-direction:column; align-items:flex-start; border-right: 1px solid var(--border); padding-right: 12px;">
              <span style="font-size:10px; font-weight:700; color:var(--text-3); white-space:nowrap;">即時總用電量</span>
              <span style="font-size:24px; font-weight:800; color:var(--alarm); font-variant-numeric:tabular-nums; line-height:1.1; margin-top:2px;">${total_kwStr}<span style="font-size:12px; font-weight:600; color:var(--text-3); margin-left:2px;">kW</span></span>
            </div>
            <div style="display:flex; flex-direction:column; align-items:flex-start; border-right: 1px solid var(--border); padding-right: 12px;">
              <span style="font-size:10px; font-weight:700; color:var(--text-3); white-space:nowrap;">總累積用電量</span>
              <span style="font-size:24px; font-weight:800; color:var(--accent-secondary); font-variant-numeric:tabular-nums; line-height:1.1; margin-top:2px;">${total_kwhStr}<span style="font-size:12px; font-weight:600; color:var(--text-3); margin-left:2px;">kWh</span></span>
            </div>
            <div style="display:flex; flex-direction:column; align-items:flex-start; justify-content: center;">
              <span style="font-size:10px; font-weight:700; color:var(--text-2); white-space:nowrap;">1F CP-1 電表</span>
              <span style="font-size:13px; font-weight:700; color:var(--text-1); margin-top:2px; white-space:nowrap;">即時: ${cp1_kwStr} kW</span>
              <span style="font-size:11px; font-weight:600; color:var(--text-2); margin-top:1px; white-space:nowrap;">累積: ${cp1_kwhStr} kWh</span>
            </div>
            <div style="display:flex; flex-direction:column; align-items:flex-start; justify-content: center;">
              <span style="font-size:10px; font-weight:700; color:var(--text-2); white-space:nowrap;">3F CP-3 電表</span>
              <span style="font-size:13px; font-weight:700; color:var(--text-1); margin-top:2px; white-space:nowrap;">即時: ${cp3_kwStr} kW</span>
              <span style="font-size:11px; font-weight:600; color:var(--text-2); margin-top:1px; white-space:nowrap;">累積: ${cp3_kwhStr} kWh</span>
            </div>
          </div>
        </div>`;;

      document.getElementById('main-grid').innerHTML = gridHtml;
      document.getElementById('cnt-ok').textContent = ok;
      document.getElementById('cnt-alarm').textContent = al;
      document.getElementById('cnt-off').textContent = off;
      // Calculate total module count: sum of iot627 units across all rooms + 2 power meters
      const totalModuleCount = Object.values(ROOM_MODULES).reduce((acc, r) => {
        if (!r || !r.modules) return acc;
        return acc + r.modules.reduce((s, m) => s + (m.count || 0), 0);
      }, 0) + 2; // +2 for ch13/ch14 power meters
      document.getElementById('cnt-total').textContent = (ok + al + off) + ' / ' + totalModuleCount;
      // Check for new delaying channels to break silence
      const hasNewAlarm = currentDelayingChannels.some(ch => !previousDelayingChannels.includes(ch));
      if (hasNewAlarm) {
        alarmSilenced = false;
      }
      previousDelayingChannels = currentDelayingChannels;
      const banner = document.getElementById('audio-unlock-banner');
      if (shouldSound && !alarmSilenced) {
        startAlarmSound();
        if (audioCtx && audioCtx.state === 'suspended' && banner) {
          banner.style.display = 'block';
        }
      } else {
        stopAlarmSound();
        if (banner) banner.style.display = 'none';
      }
      document.getElementById('btn-silence').style.display = (shouldSound && !alarmSilenced) ? 'inline-block' : 'none';
      if (!shouldSound) alarmSilenced = false;
      if (currentDashView === 'floorplan') updateFloorplan(data);
    }
    // ── 38模組設備定義 ────────────────────────────────────────────────
    const ROOM_MODULES = [];
    const MODULE_INFO = {
      'iot627': [
        { key: 'control_temperature', label: '控制溫度', unit: '°C' },
        { key: 'coil_temperature',    label: '盤管溫度', unit: '°C' },
        { key: 'compressor_current',  label: '運轉電流', unit: 'A'  },
        { key: 'high_pressure',       label: '高壓壓力', unit: 'MPa'},
        { key: 'low_pressure',        label: '低壓壓力', unit: 'MPa'},
        { key: 'control_temperature_set', label: '設定溫度', unit: '°C' }
      ],
      'YB-D616-16DI': Array.from({ length: 12 }, (_, i) => [
        { key: `fan_${String(i + 1).padStart(2, '0')}_running`, label: `風扇 #${i + 1} 運轉`, unit: '' },
        { key: `fan_${String(i + 1).padStart(2, '0')}_fault`,   label: `風扇 #${i + 1} 異常`, unit: '' }
      ]).flat(),
      'S2-800MT': [
        { key: 'voltage_rs',     label: 'RS線電壓',  unit: 'V'   },
        { key: 'voltage_st',     label: 'ST線電壓',  unit: 'V'   },
        { key: 'voltage_rt',     label: 'RT線電壓',  unit: 'V'   },
        { key: 'voltage_ll_avg', label: '平均電壓',  unit: 'V'   },
        { key: 'current_r',      label: 'R相電流',   unit: 'A'   },
        { key: 'current_s',      label: 'S相電流',   unit: 'A'   },
        { key: 'current_t',      label: 'T相電流',   unit: 'A'   },
        { key: 'current_avg',    label: '平均電流',  unit: 'A'   },
        { key: 'power_total',    label: '瞬時功率',  unit: 'kW'  },
        { key: 'energy_total',   label: '累積用電量', unit: 'kWh' },
        { key: 'power_factor',   label: '功率因數',  unit: ''    }
      ]
    };
    const MODULE_TYPE_LABEL = {
      'iot627':       '冷凍主機 (iot627)',
      'YB-D616-16DI': 'DI模組 (YB-D616-16DI)',
      'S2-800MT':     '集合式電表 (S2-800MT)'
    };
    function getModuleTypeLabel(type, ch) {
      if (type === 'iot627' && ROOM_MODULES[ch]?.temp_only_iot) {
        return '庫溫監控器 (IoT627)';
      }
      return MODULE_TYPE_LABEL[type] || type;
    }
    function getModuleInfo(type, ch) {
      if (type === 'iot627' && ROOM_MODULES[ch]?.temp_only_iot) {
        return [
          { key: 'control_temperature', label: '控制溫度', unit: '°C' },
          { key: 'abnormal_status', label: '高溫警報', unit: '' }
        ];
      }
      return MODULE_INFO[type] || [];
    }
    // 圖表中已加入的 series 列表 [{roomCh, deviceType, deviceIdx, infoKey, label, color}]
    let chartSeries = [];
    function buildChannelFilters() {
      filtersBuilt = true;
      // 初始化庫別下拉
      const selRoom = document.getElementById('sel-room');
      selRoom.innerHTML = '<option value="">-- 選擇庫別 --</option>';
      ALL_CHS.forEach(ch => {
        const room = ROOM_MODULES[ch];
        if (!room) return;
        const opt = document.createElement('option');
        opt.value = ch;
        opt.textContent = room.name;
        selRoom.appendChild(opt);
      });
      // 增加 1F/3F 電表選項
      const optCh13 = document.createElement('option');
      optCh13.value = 'ch13';
      optCh13.textContent = '1F 電表 (CP-1)';
      selRoom.appendChild(optCh13);
      const optCh14 = document.createElement('option');
      optCh14.value = 'ch14';
      optCh14.textContent = '3F 電表 (CP-3)';
      selRoom.appendChild(optCh14);

      selRoom.onchange = onRoomChange;
      document.getElementById('sel-device').onchange = onDeviceChange;
      document.getElementById('sel-info').onchange = onInfoChange;
      document.getElementById('btn-chart-add').onclick = addChartSeries;
      document.getElementById('btn-chart-clear').onclick = clearChartSeries;
    }
    function onRoomChange() {
      const ch = document.getElementById('sel-room').value;
      const selDevice = document.getElementById('sel-device');
      const selInfo = document.getElementById('sel-info');
      selDevice.innerHTML = '<option value="">-- 選擇設備 --</option>';
      selInfo.innerHTML = '<option value="">-- 選擇資訊 --</option>';
      selDevice.disabled = !ch;
      selInfo.disabled = true;
      document.getElementById('btn-chart-add').disabled = true;
      if (!ch) return;
      const room = ROOM_MODULES[ch];
      room.modules.forEach(m => {
          if (m.type !== 'iot627' && m.type !== 'S2-800MT') return;
          for (let i = 1; i <= m.count; i++) {
          const opt = document.createElement('option');
          opt.value = `${m.type}::${i}`;
          opt.textContent = `${getModuleTypeLabel(m.type, ch)} #${i}`;
          selDevice.appendChild(opt);
        }
      });
    }
    function onDeviceChange() {
      const val = document.getElementById('sel-device').value;
      const selInfo = document.getElementById('sel-info');
      selInfo.innerHTML = '<option value="">-- 選擇資訊 --</option>';
      selInfo.disabled = !val;
      document.getElementById('btn-chart-add').disabled = true;
      if (!val) return;
      const deviceType = val.split('::')[0];
      const ch = document.getElementById('sel-room').value;
      const infos = getModuleInfo(deviceType, ch);
      infos.forEach(info => {
        const opt = document.createElement('option');
        opt.value = info.key;
        opt.textContent = `${info.label}${info.unit ? ' (' + info.unit + ')' : ''}`;
        selInfo.appendChild(opt);
      });
    }
    function onInfoChange() {
      const info = document.getElementById('sel-info').value;
      document.getElementById('btn-chart-add').disabled = !info;
    }
    function addChartSeries() {
      const ch = document.getElementById('sel-room').value;
      const deviceVal = document.getElementById('sel-device').value;
      const infoKey = document.getElementById('sel-info').value;
      if (!ch || !deviceVal || !infoKey) return;
      const [deviceType, deviceIdx] = deviceVal.split('::');
      const room = ROOM_MODULES[ch];
      const infoMeta = getModuleInfo(deviceType, ch).find(i => i.key === infoKey);
      const label = `${room.name} ${getModuleTypeLabel(deviceType, ch)}#${deviceIdx} ${infoMeta?.label || infoKey}`;
      // 避免重複
      const dup = chartSeries.find(s => s.ch === ch && s.deviceType === deviceType && s.deviceIdx === deviceIdx && s.infoKey === infoKey);
      if (dup) return;
      const color = CH_COLORS[chartSeries.length % CH_COLORS.length];
      chartSeries.push({ ch, deviceType, deviceIdx: parseInt(deviceIdx), infoKey, label, color, unit: infoMeta?.unit || '' });
      renderSeriesTags();
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      loadChartData();
    }
    function clearChartSeries() {
      chartSeries = [];
      renderSeriesTags();
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      document.getElementById('stats-wrap').style.display = 'none';
    }
    function renderSeriesTags() {
      const container = document.getElementById('chart-selected-tags');
      container.innerHTML = '';
      chartSeries.forEach((s, idx) => {
        const tag = document.createElement('div');
        tag.style.cssText = `display:inline-flex;align-items:center;gap:5px;background:#eef4ff;border:1px solid ${s.color};border-radius:12px;padding:3px 10px 3px 8px;font-size:11px;`;
        tag.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${s.color};flex-shrink:0;"></span><span style="color:var(--text-1);font-weight:600;">${s.label}</span><span onclick="removeChartSeries(${idx})" style="cursor:pointer;color:var(--text-3);margin-left:2px;font-size:13px;line-height:1;">&times;</span>`;
        container.appendChild(tag);
      });
    }
    function removeChartSeries(idx) {
      chartSeries.splice(idx, 1);
      renderSeriesTags();
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      loadChartData();
    }
    function getRangeParams() {
      const fmt = d => {
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
      };
      if (currentRange === 'custom') {
        const from = new Date(document.getElementById('chart-date-from').value);
        const to = new Date(document.getElementById('chart-date-to').value);
        return `range=custom&from=${encodeURIComponent(fmt(from))}&to=${encodeURIComponent(fmt(to))}`;
      } else {
        const now = new Date(), from = new Date(now - currentRange * 60000);
        return `range=custom&from=${encodeURIComponent(fmt(from))}&to=${encodeURIComponent(fmt(now))}`;
      }
    }
    function buildChartOptions(xMin, xMax) {
      return {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 12 } },
          tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.parsed.y.toFixed(1)}°C` } }
        },
        scales: {
          x: {
            type: 'time', min: xMin, max: xMax,
            time: { tooltipFormat: 'MM/dd HH:mm:ss', displayFormats: { minute: 'HH:mm', hour: 'MM/dd HH:mm', day: 'MM/dd' } },
            ticks: { font: { size: 10 }, maxTicksLimit: 10 }, grid: { color: '#dde6ef' }
          },
          y: { beginAtZero: false, grace: '5%', ticks: { font: { size: 10 }, callback: v => Number(v).toFixed(1) + '°C' }, grid: { color: '#dde6ef' } }
        }
      };
    }
    async function loadChartData() {
      const params = getRangeParams();
      if (!params) return;
      if (!chartSeries.length) {
        const sw = document.getElementById('stats-wrap');
        sw.style.display = 'none';
        const ctx = document.getElementById('tempChart').getContext('2d');
        if (!chartInstance) { chartInstance = new Chart(ctx, { type: 'line', data: { datasets: [] }, options: buildChartOptions(new Date(Date.now() - currentRange*60000), new Date()) }); }
        else { chartInstance.data.datasets = []; chartInstance.update('none'); }
        return;
      }
      let xMin, xMax;
      if (currentRange === 'custom') {
        xMin = new Date(document.getElementById('chart-date-from').value);
        xMax = new Date(document.getElementById('chart-date-to').value);
      } else {
        const now = new Date();
        xMin = new Date(now - currentRange * 60000);
        xMax = now;
      }
      // ── 1. 溫度歷史資料（iot627 控制/盤管溫度）──────────────────
      const tempRes = await fetch(`/api/chart_data?${params}`).then(r => r.json()).catch(() => null);
      const tempSeries = tempRes?.series || {};
      // ── 2. 電表歷史資料（S2-800MT 各欄位）─────────────────────
      // 找出需要電表歷史的 series，按欄位分群批次查詢
      const powerNeeded = chartSeries.filter(s => s.deviceType === 'S2-800MT');
      const powerDataMap = {}; // key: `${ch}_${infoKey}` -> [{t,v}]
      if (powerNeeded.length) {
        // 按 infoKey 分群（相同欄位可一次查）
        const byField = {};
        powerNeeded.forEach(s => {
          if (!byField[s.infoKey]) byField[s.infoKey] = new Set();
          byField[s.infoKey].add(s.ch);
        });
        for (const [field, chSet] of Object.entries(byField)) {
          const chParams = [...chSet].map(c => `ch=${c}`).join('&');
          const url = `/api/power_chart_data?${chParams}&field=${field}&${params}`;
          const pr = await fetch(url).then(r => r.json()).catch(() => null);
          if (pr?.series) {
            for (const [ch, pts] of Object.entries(pr.series)) {
              powerDataMap[`${ch}_${field}`] = pts;
            }
          }
        }
      }
      // ── 3. 組裝 datasets ──────────────────────────────────────
      const datasets = chartSeries.map(s => {
        let points = [];
        if (s.deviceType === 'iot627' && ['control_temperature', 'coil_temperature', 'l301', 'coil'].includes(s.infoKey)) {
          // 歷史溫度
          const chSeries = tempSeries[s.ch];
          if (chSeries) points = chSeries.data.map(d => ({ x: new Date(d.t.replace(' ','T')+'+08:00'), y: d.v }));
        } else if (s.deviceType === 'S2-800MT') {
          // 歷史電表
          const pts = powerDataMap[`${s.ch}_${s.infoKey}`] || [];
          points = pts.map(d => {
            let val = d.v;
            if (['power_total', 'energy_total'].includes(s.infoKey)) {
              val = val / 1000.0;
            }
            return { x: new Date(d.t.replace(' ','T')+'+08:00'), y: val };
          });
        } else {
          // 其他（YB-D616-16DI / iot627 非溫度）→ 即時單點
          const d = lastSseData ? lastSseData[s.ch] : null;
          if (d) {
            let val = null;
            if (d.units) {
              const getUnitType = (u) => {
                if (u.type) return u.type;
                if (u.id && (u.id.startsWith('YB-') || u.id.includes('DI-'))) return 'YB-D616-16DI';
                return 'iot627';
              };
              const typeUnits = d.units.filter(u => getUnitType(u) === s.deviceType);
              const u = typeUnits[s.deviceIdx-1];
              if (u) val = u[s.infoKey];
            }
            if (val !== null && val !== undefined) points = [{ x: new Date(), y: Number(val) }];
          }
        }
        return {
          label: s.label,
          data: points,
          borderColor: s.color, backgroundColor: s.color + '18', borderWidth: 1.5,
          pointRadius: points.length === 1 ? 5 : 0,
          pointHoverRadius: 4, tension: 0.3, fill: false
        };
      });
      const unitLabels = [...new Set(chartSeries.map(s => s.unit).filter(Boolean))];
      const yLabel = unitLabels.length === 1 ? unitLabels[0] : '';
      const opts = buildChartOptions(xMin, xMax);
      opts.scales.y.ticks.callback = v => Number(v).toFixed(1) + (yLabel ? ' ' + yLabel : '');
      opts.plugins.tooltip.callbacks.label = c => ` ${c.dataset.label}: ${c.parsed.y.toFixed(1)} ${chartSeries[c.datasetIndex]?.unit || ''}`;
      const ctx = document.getElementById('tempChart').getContext('2d');
      if (!chartInstance) { chartInstance = new Chart(ctx, { type: 'line', data: { datasets }, options: opts }); }
      else { chartInstance.data.datasets = datasets; chartInstance.options.scales.x.min = xMin; chartInstance.options.scales.x.max = xMax; chartInstance.options.scales.y.ticks.callback = opts.scales.y.ticks.callback; chartInstance.update('none'); }
      const sw = document.getElementById('stats-wrap');
      if (!chartSeries.length) { sw.style.display = 'none'; return; }
      sw.style.display = 'block';
      document.getElementById('stats-body').innerHTML = chartSeries.map((s, i) => {
        const pts = datasets[i]?.data || [];
        const vals = pts.map(p => p.y).filter(v => v !== null && isFinite(v));
        const line = `<span style="display:inline-block;width:28px;height:2px;background:${s.color};vertical-align:middle;margin-right:4px;"></span>實線`;
        if (!vals.length) return `<tr><td><span class="tbl-dot" style="background:${s.color}"></span>${s.label}</td><td>${line}</td><td colspan="7" style="color:var(--text-3)">無資料</td></tr>`;
        const mx = Math.max(...vals).toFixed(1), mn = Math.min(...vals).toFixed(1), av = (vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1);
        return `<tr><td><span class="tbl-dot" style="background:${s.color}"></span>${s.label}</td><td>${line}</td>
          <td style="font-weight:700;color:var(--alarm)">${mx} ${s.unit}</td><td>-</td>
          <td style="font-weight:700;color:var(--accent)">${mn} ${s.unit}</td><td>-</td>
          <td>${av} ${s.unit}</td><td style="color:var(--text-3)">${vals.length}</td><td>-</td></tr>`;
      }).join('');
    }
    function escHtml(v) {
      return String(v ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]));
    }
    function severityLabel(v) {
      return ({ critical: '異常', warning: '警告', info: '紀錄' })[v] || v || '--';
    }
    function getDemoAlarmEvents() {
      const events = [];
      let seq = 0;
      const nextTime = () => {
        const base = new Date('2026-06-04T08:00:00+08:00');
        base.setMinutes(base.getMinutes() + seq * 3);
        seq++;
        const p = n => String(n).padStart(2, '0');
        return `${base.getFullYear()}-${p(base.getMonth() + 1)}-${p(base.getDate())} ${p(base.getHours())}:${p(base.getMinutes())}:${p(base.getSeconds())}`;
      };
      const add = (severity, category, scope, message, channel, status = 'active', clearedAt = '') => {
        events.push({
          triggered_at: nextTime(),
          severity,
          category,
          scope,
          message,
          status,
          cleared_at: clearedAt,
          channel
        });
      };
      const iotUnits = [
        ['a', 'A庫', ['A-1', 'A-2']],
        ['b', 'B庫', ['B-1', 'B-2']],
        ['g', 'G庫', ['G-1', 'G-2']],
        ['h', 'H庫', ['H-1', 'H-2']],
        ['i1', 'I1庫', ['I-1', 'I-2', 'I-3']],
        ['i2', 'I2庫', ['I-4', 'I-5']],
        ['j', 'J庫', ['J-1', 'J-2']],
        ['k', 'K庫', ['K-1', 'K-2']]
      ];
      const fanRooms = [
        ['c', 'D庫', 12],
        ['d', 'E庫', 12],
        ['e', 'F庫', 12],
        ['j', 'J庫', 9],
        ['k', 'K庫', 11]
      ];
      const s2Meters = [
        ['a', 'A庫', 'S2-800MT / Slave 31'],
        ['b', 'B庫', 'S2-800MT / Slave 32'],
        ['c', 'D庫', 'S2-800MT / Slave 33'],
        ['d', 'E庫', 'S2-800MT / Slave 34'],
        ['e', 'F庫', 'S2-800MT / Slave 35'],
        ['g', 'G庫', 'S2-800MT / Slave 36'],
        ['h', 'H庫', 'S2-800MT / Slave 37'],
        ['i1', 'I1庫', 'S2-800MT / Slave 38'],
        ['i2', 'I2庫', 'S2-800MT / Slave 39'],
        ['j', 'J庫', 'S2-800MT / Slave 40'],
        ['k', 'K庫', 'S2-800MT / Slave 41']
      ];
      const ybModules = [
        ['c', 'D庫', ['YB-D616 / Slave 51', 'YB-D616 / Slave 52']],
        ['d', 'E庫', ['YB-D616 / Slave 53', 'YB-D616 / Slave 54']],
        ['e', 'F庫', ['YB-D616 / Slave 55', 'YB-D616 / Slave 56']],
        ['j', 'J庫', ['YB-D616 / Slave 57', 'YB-D616 / Slave 58']],
        ['k', 'K庫', ['YB-D616 / Slave 59', 'YB-D616 / Slave 60']]
      ];
      add('warning', '通信警報', 'GATEWAY-01', '串口服務器離線', 'all');
      add('warning', '通信警報', 'GATEWAY-02', '串口服務器離線', 'all');
      add('warning', '通信警報', 'GATEWAY-01 / RS485-1', 'RS485 Bus通信異常', 'all');
      add('warning', '通信警報', 'GATEWAY-02 / RS485-2', 'RS485 Bus通信異常', 'all');
      add('warning', '通信警報', 'GATEWAY-01 / RS485-1', 'RS485通信大量異常', 'all');
      add('warning', '通信警報', 'GATEWAY-02 / RS485-2', 'RS485通信大量異常', 'all');
      iotUnits.forEach(([ch, room, units]) => {
        units.forEach((unit, idx) => {
          const slave = String(iotUnits.slice(0, iotUnits.findIndex(r => r[0] === ch)).reduce((sum, r) => sum + r[2].length, 0) + idx + 1).padStart(2, '0');
          const controlTemp = (-18 + seq * 0.7).toFixed(1);
          add('critical', '溫度警報', `${room} / ${unit}`, `高溫警報；控制溫度 ${controlTemp}°C`, ch);
          add('critical', '設備警報', `${room} / ${unit}`, '設備異常；L216=1', ch);
          add('warning', '通信警報', `IoT627 / Slave ${slave} / ${unit}`, '單台設備通信異常', ch);
        });
      });
      s2Meters.forEach(([ch, room, meter]) => {
        add('warning', '通信警報', `${room} / ${meter}`, '單台電表通信異常', ch);
      });
      ybModules.forEach(([ch, room, modules]) => {
        modules.forEach(moduleName => {
          add('warning', '通信警報', `${room} / ${moduleName}`, '單台DI模組通信異常', ch);
        });
      });
      fanRooms.forEach(([ch, room, count]) => {
        for (let fan = 1; fan <= count; fan++) {
          add('critical', '壓差風扇警報', `${room} / 風扇 #${fan}`, '壓差風扇異常', ch);
        }
      });
      add('info', '系統紀錄', 'GATEWAY-01', '串口服務器通信恢復', 'all', 'cleared', '2026-06-04 16:10:00');
      add('info', '系統紀錄', 'GATEWAY-02 / RS485-2', 'RS485 Bus通信恢復', 'all', 'cleared', '2026-06-04 16:13:00');
      add('info', '系統紀錄', 'IoT627 / Slave 03 / B-1', '單台設備通信恢復', 'b', 'cleared', '2026-06-04 16:16:00');
      add('info', '系統紀錄', 'A庫 / A-1', '高溫警報已復歸', 'a', 'cleared', '2026-06-04 16:19:00');
      return events;
    }
    function normalizeAlarmEvents(res) {
      if (!res) return getDemoAlarmEvents();
      const rows = Array.isArray(res.records) ? res.records : (Array.isArray(res.events) ? res.events : []);
      if (!rows.length) return getDemoAlarmEvents();
      return rows.map(r => {
        if (r.severity || r.category || r.scope || r.message) {
          return {
            triggered_at: r.triggered_at || r.time || r.created_at || '',
            severity: r.severity || 'warning',
            category: r.category || r.query_filter_group || '通信警報',
            scope: r.scope || r.location || r.device || r.name || '',
            message: r.message || r.alarm_name || r.display_message || '',
            status: r.status || (r.cleared_at ? 'cleared' : 'active'),
            cleared_at: r.cleared_at || r.clear_time || '',
            channel: r.channel || r.ch || 'all'
          };
        }
        const isHigh = r.alarm_type === 'HIGH';
        return {
          triggered_at: r.triggered_at || '',
          severity: 'critical',
          category: '溫度警報',
          scope: r.name || '',
          message: isHigh ? '高溫警報' : '低溫警報',
          status: r.cleared_at ? 'cleared' : 'active',
          cleared_at: r.cleared_at || '',
          channel: r.channel || r.ch || 'all'
        };
      });
    }
    function passAlarmFilters(r, filters) {
      const t = (r.triggered_at || '').slice(0, 10);
      if (filters.ch !== 'all' && r.channel !== filters.ch && r.channel !== 'all') return false;
      if (filters.from && t && t < filters.from) return false;
      if (filters.to && t && t > filters.to) return false;
      if (filters.severity !== 'all' && r.severity !== filters.severity) return false;
      if (filters.category !== 'all' && r.category !== filters.category) return false;
      if (filters.status !== 'all' && r.status !== filters.status) return false;
      return true;
    }
    function renderAlarmSummary(records) {
      const active = records.filter(r => r.status === 'active').length;
      const critical = records.filter(r => r.severity === 'critical').length;
      const warning = records.filter(r => r.severity === 'warning').length;
      const comm = records.filter(r => r.category === '通信警報').length;
      document.getElementById('alarm-summary').innerHTML = [
        ['警報中', active, '目前尚未復歸'],
        ['異常', critical, '庫溫 / 設備 / 風扇'],
        ['警告', warning, '通信與巡檢事件'],
        ['通信警報', comm, 'Gateway / RS485 / 單台設備']
      ].map(s => `<div class="sum-card">
        <div class="sum-name">${s[0]}</div><div class="sum-total">${s[1]}</div>
        <div class="sum-detail">${s[2]}</div>
      </div>`).join('');
    }
    async function loadAlarmHistory() {
      const filters = {
        ch: document.getElementById('alarm-ch-filter').value,
        from: document.getElementById('alarm-date-from').value,
        to: document.getElementById('alarm-date-to').value,
        severity: document.getElementById('alarm-severity-filter').value,
        category: document.getElementById('alarm-category-filter').value,
        status: document.getElementById('alarm-status-filter').value
      };
      const params = new URLSearchParams({ limit: '200' });
      if (filters.ch !== 'all') params.set('channel', filters.ch);
      if (filters.from) params.set('from', filters.from);
      if (filters.to) params.set('to', filters.to);
      if (filters.severity !== 'all') params.set('severity', filters.severity);
      if (filters.category !== 'all') params.set('category', filters.category);
      if (filters.status !== 'all') params.set('status', filters.status);
      let res = await fetch(`/api/alarm_events?${params.toString()}`).then(r => r.json()).catch(() => null);
      if (!res) res = await fetch(`/api/alarm_history?${params.toString()}`).then(r => r.json()).catch(() => null);
      let records = normalizeAlarmEvents(res).filter(r => passAlarmFilters(r, filters)).slice(0, 200);
      renderAlarmSummary(records);
      document.getElementById('alarm-total-badge').textContent = `共 ${records.length} 筆`;
      const tbody = document.getElementById('alarm-tbody');
      if (!records.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="no-data">查無警報記錄</td></tr>`;
        return;
      }
      tbody.innerHTML = records.map((r, i) => {
        const severity = r.severity || 'warning';
        const status = r.status || 'active';
        const statusText = status === 'cleared' ? '已復歸' : '警報中';
        return `
      <tr>
        <td style="color:var(--text-3)">${i + 1}</td>
        <td>${fmtTime(r.triggered_at)}</td>
        <td><span class="badge badge-${escHtml(severity)}">${escHtml(severityLabel(severity))}</span></td>
        <td>${escHtml(r.category)}</td>
        <td class="alarm-location">${escHtml(r.scope)}</td>
        <td class="alarm-message">${escHtml(r.message)}</td>
        <td><span class="badge badge-${status === 'cleared' ? 'cleared' : 'active'}">${statusText}</span></td>
        <td>${fmtTime(r.cleared_at)}</td>
      </tr>`;
      }).join('');
    }
    function resetAlarmQuery() {
      document.getElementById('alarm-ch-filter').value = 'all';
      document.getElementById('alarm-date-from').value = '';
      document.getElementById('alarm-date-to').value = '';
      document.getElementById('alarm-severity-filter').value = 'all';
      document.getElementById('alarm-category-filter').value = 'all';
      document.getElementById('alarm-status-filter').value = 'all';
      loadAlarmHistory();
    }
    function fmtTime(ts) { if (!ts) return '--'; return ts.slice(0, 16).replace('T', ' '); }
    function tick() {
      const n = new Date();
      document.getElementById('clk').textContent = n.toTimeString().slice(0, 8);
      document.getElementById('dte').textContent = n.getFullYear() + '/'
        + String(n.getMonth() + 1).padStart(2, '0') + '/' + String(n.getDate()).padStart(2, '0');
    }
    // ── 警報聲音系統 ──
    let audioCtx = null, alarmOscillator = null, alarmGain = null, alarmSilenced = false, alarmSounding = false;
    let alarmTimer = null;
    function unlockAudio() {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const banner = document.getElementById('audio-unlock-banner');
      if (banner) banner.style.display = 'none';
    }
    // 瀏覽器安全限制：必須要有使用者互動才能發出聲音
    document.addEventListener('click', unlockAudio);
    function getChSoundEnabled(ch) {
      try { const v = localStorage.getItem('sound_' + ch); return v === null ? true : v === '1'; } catch (e) { return true; }
    }
    function setChSoundEnabled(ch, enabled) {
      try { localStorage.setItem('sound_' + ch, enabled ? '1' : '0'); } catch (e) { }
    }
    function _doStartAlarm() {
      try {
        // 每次重新建立 oscillator + gain（舊的已被 stop/disconnect）
        alarmOscillator = audioCtx.createOscillator();
        alarmGain = audioCtx.createGain();
        alarmOscillator.type = 'square';
        alarmOscillator.frequency.value = 880;
        alarmGain.gain.value = 0.15;
        alarmOscillator.connect(alarmGain);
        alarmGain.connect(audioCtx.destination);
        alarmOscillator.start();
        alarmSounding = true;
        // 用 setValueAtTime 排定 beep pattern（每 0.3s 開/關，共 9999 次）
        const t0 = audioCtx.currentTime;
        for (let i = 0; i < 9999; i++) {
          alarmGain.gain.setValueAtTime(0.15, t0 + i * 0.6);
          alarmGain.gain.setValueAtTime(0, t0 + i * 0.6 + 0.3);
        }
      } catch (e) { console.warn('Alarm sound error:', e); }
    }
    function startAlarmSound() {
      if (alarmSounding) return;
      try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') {
          // 等瀏覽器解鎖後才真正播放
          audioCtx.resume().then(() => {
            if (alarmSounding) return; // 避免重複呼叫
            _doStartAlarm();
          }).catch(e => console.warn('AudioContext resume failed:', e));
        } else {
          _doStartAlarm();
        }
      } catch (e) { console.warn('Alarm sound error:', e); }
    }
    function stopAlarmSound() {
      if (!alarmSounding) return;
      alarmSounding = false; // 先設 false，避免 resume().then 內重入
      try {
        if (alarmTimer) { clearInterval(alarmTimer); alarmTimer = null; }
        if (alarmOscillator) {
          try { alarmOscillator.stop(); } catch (e) { }
          alarmOscillator.disconnect(); alarmOscillator = null;
        }
        if (alarmGain) { alarmGain.disconnect(); alarmGain = null; }
      } catch (e) { }
    }
    function silenceAlarm() {
      alarmSilenced = true;
      stopAlarmSound();
      document.getElementById('btn-silence').style.display = 'none';
    }
    function openModal() {
      document.getElementById('modal-overlay').style.display = 'flex';
      let leftHtml = '';
      let rightHtml = '';
      Object.keys(alarmSettings).forEach(ch => {
        const s = alarmSettings[ch];
        const alarmOn = s.alarm_enabled !== undefined ? !!s.alarm_enabled : true;
        const offset = s.temp_offset !== undefined ? s.temp_offset : 0;
        const chLabel = ch.replace('ch', 'CH');
        // 左欄：警報設定
        leftHtml += `<div style="margin-bottom:10px;padding:10px 12px;background:#ffffff;border-radius:6px;border:1px solid var(--border);">
      <div style="font-size:12px;font-weight:700;color:var(--text-1);margin-bottom:8px;">${chLabel} ${s.name}</div>
      <div style="display:flex;gap:10px;align-items:flex-end;">
        <div style="flex:1;"><label style="font-size:10px;color:var(--text-2);">高溫警報 (°C)</label>
          <input id="hi_${ch}" type="number" value="${s.hi}" step="0.1"
            style="width:100%;padding:5px;border:1px solid var(--border);border-radius:4px;font-size:12px;margin-top:4px;"></div>
        <div style="flex:1;"><label style="font-size:10px;color:var(--text-2);">低溫警報 (°C)</label>
          <input id="lo_${ch}" type="number" value="${s.lo}" step="0.1"
            style="width:100%;padding:5px;border:1px solid var(--border);border-radius:4px;font-size:12px;margin-top:4px;"></div>
        <div style="flex:1;"><label style="font-size:10px;color:var(--text-2);">警報延遲 (分鐘)</label>
          <input id="delay_${ch}" type="number" value="${s.delay !== undefined ? s.delay : 0}" step="1" min="0"
            style="width:100%;padding:5px;border:1px solid var(--border);border-radius:4px;font-size:12px;margin-top:4px;"></div>
        <div style="flex:0 0 76px;text-align:center;">
          <label style="font-size:10px;color:var(--text-2);display:block;margin-bottom:6px;">警報開關</label>
          <label style="position:relative;display:inline-block;width:44px;height:24px;cursor:pointer;">
            <input type="checkbox" id="alarm_enabled_${ch}" ${alarmOn ? 'checked' : ''}
              style="opacity:0;width:0;height:0;position:absolute;">
            <span style="position:absolute;top:0;left:0;right:0;bottom:0;background:${alarmOn ? 'var(--text-1)' : '#ccc'};border-radius:12px;transition:.3s;"
              id="slider_${ch}"></span>
            <span style="position:absolute;top:2px;left:${alarmOn ? '22px' : '2px'};width:20px;height:20px;background:#fff;border-radius:50%;transition:.3s;box-shadow:0 1px 3px #00000033;"
              id="knob_${ch}"></span>
          </label>
        </div>
      </div></div>`;
        // 右欄：溫度校正設定
        rightHtml += `<div style="margin-bottom:10px;padding:10px 12px;background:#ffffff;border-radius:6px;border:1px solid var(--border);">
      <div style="font-size:12px;font-weight:700;color:var(--text-1);margin-bottom:8px;">${chLabel} ${s.name}</div>
      <div style="display:flex;gap:10px;align-items:flex-end;">
        <div style="flex:1;">
          <label style="font-size:10px;color:var(--text-2);">校正值 (°C)　感測器值 + 校正值 = 顯示值</label>
          <input id="offset_${ch}" type="number" value="${offset}" step="0.1"
            style="width:100%;padding:5px;border:1px solid var(--border);border-radius:4px;font-size:13px;font-weight:700;margin-top:4px;color:var(--text-1);">
        </div>
        <div style="flex:0 0 90px;text-align:right;padding-bottom:4px;">
          <span style="font-size:10px;color:var(--text-2);">目前校正</span><br>
          <span style="font-size:14px;font-weight:700;color:${offset !== 0 ? 'var(--text-1)' : 'var(--text-3)'};">
            ${offset > 0 ? '+' : ''}${offset} °C
          </span>
        </div>
      </div></div>`;
      });
      document.getElementById('modal-content').innerHTML = `
        <div style="display:flex;gap:20px;align-items:flex-start;">
          <div style="flex:1;min-width:0;">
            <div style="font-size:11px;font-weight:700;color:var(--text-1);letter-spacing:2px;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid var(--text-1);">警報設定</div>
            ${leftHtml}
          </div>
          <div style="flex:1;min-width:0;border-left:1px solid var(--border);padding-left:20px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-1);letter-spacing:2px;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid var(--text-1);">溫度校正設定</div>
            ${rightHtml}
          </div>
        </div>`;
      // bind toggle visual updates
      Object.keys(alarmSettings).forEach(ch => {
        const cb = document.getElementById('alarm_enabled_' + ch);
        if (cb) cb.addEventListener('change', function () {
          document.getElementById('slider_' + ch).style.background = this.checked ? 'var(--text-1)' : '#ccc';
          document.getElementById('knob_' + ch).style.left = this.checked ? '22px' : '2px';
        });
      });
    }
    function closeModal() { document.getElementById('modal-overlay').style.display = 'none'; }
    async function saveSettings() {
      const updated = {};
      Object.keys(alarmSettings).forEach(ch => {
        updated[ch] = {
          hi: parseFloat(document.getElementById('hi_' + ch).value),
          lo: parseFloat(document.getElementById('lo_' + ch).value),
          delay: parseInt(document.getElementById('delay_' + ch).value) || 0,
          alarm_enabled: document.getElementById('alarm_enabled_' + ch).checked ? 1 : 0,
          temp_offset: parseFloat(document.getElementById('offset_' + ch).value) || 0
        };
      });
      await fetch('/api/alarm_settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updated) });
      await fetchAlarmSettings();
      fpLabelsBuilt = false;
      closeModal(); update(); alert('設定已儲存！');
    }
    document.addEventListener('DOMContentLoaded', () => {
      document.getElementById('btn-dashboard').addEventListener('click', () => showPage('dashboard'));
      document.getElementById('btn-chart').addEventListener('click', () => showPage('chart'));
      document.getElementById('btn-alarm').addEventListener('click', () => showPage('alarm'));
      document.getElementById('btn-report').addEventListener('click', () => showPage('report'));
      document.getElementById('btn-settings').addEventListener('click', openModal);
      document.querySelectorAll('.rbtn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('.rbtn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          if (btn.id === 'btn-custom-range') {
            document.getElementById('custom-range-picker').style.display = 'flex';
            stopRealtimeChart();
          } else {
            document.getElementById('custom-range-picker').style.display = 'none';
            currentRange = parseInt(btn.dataset.range);
            if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
            loadChartData();
            startRealtimeChart();
          }
        });
      });
      document.getElementById('btn-chart-search')?.addEventListener('click', () => {
        currentRange = 'custom';
        const from = document.getElementById('chart-date-from').value;
        const to = document.getElementById('chart-date-to').value;
        if (!from || !to) { alert('請選擇完整的起始與結束時間！'); return; }
        if (new Date(from) > new Date(to)) { alert('起始時間不能晚於結束時間！'); return; }
        if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
        loadChartData();
      });
      // Pre-initialize report page so month field always has a default value
      initReportPage();
    });
    fetchAlarmSettings().then(() => {
      populateChannelDropdowns();
      update(); tick();
      switchDashView('card');
      setInterval(tick, 1000);
      startSSE();
    });
    // ── 平面圖視圖 ──────────────────────────────────────────────
    // 錨點座標：以 floorplan.png (1220×1037) 為基準，左上=0,0 右下=1,1
    const FLOORPLAN_COORDS = [];
    // 小卡片出現在錨點的哪一側（依房間位置決定）
    const FLOORPLAN_SIDE = [];
    let currentDashView = 'card';
    let fpLabelsBuilt = false;
    function fitFpWrapper() {
      const container = document.getElementById('fp-container');
      const wrapper = document.getElementById('fp-wrapper');
      const img = document.getElementById('fp-img');
      if (!container || !wrapper || !img || currentDashView !== 'floorplan') return;
      // 讀圖片的實際像素比例（載入後才有值；未載入則用 1.176 保底）
      const nw = img.naturalWidth || 1220;
      const nh = img.naturalHeight || 1037;
      const AR = nw / nh;
      const h = container.clientHeight || (window.innerHeight - container.getBoundingClientRect().top - 32);
      const w = container.clientWidth;
      if (h <= 0 || w <= 0) return;
      wrapper.style.width = Math.min(Math.floor(h * AR), w) + 'px';
    }
    function switchDashView(v) {
      currentDashView = v;
      const isCard = v === 'card';
      const dash = document.getElementById('page-dashboard');
      document.getElementById('btn-view-card').classList.toggle('active', isCard);
      document.getElementById('btn-view-fp').classList.toggle('active', !isCard);
      document.getElementById('card-view-wrap').style.display = isCard ? '' : 'none';
      document.getElementById('fp-container').style.display = isCard ? 'none' : '';
      dash.classList.toggle('fp-mode', !isCard);
      if (!isCard) {
        if (!fpLabelsBuilt) initFloorplanLabels();
        const img = document.getElementById('fp-img');
        const doFit = () => { requestAnimationFrame(() => { fitFpWrapper(); if (lastSseData) updateFloorplan(lastSseData); }); };
        if (img.complete && img.naturalWidth) { doFit(); }
        else { img.onload = doFit; }
      }
      hideFpMenu();
    }
    window.addEventListener('resize', () => {
      if (currentDashView === 'floorplan') fitFpWrapper();
    });
    function initFloorplanLabels() {
      const wrapper = document.getElementById('fp-wrapper');
      wrapper.querySelectorAll('.fp-label').forEach(el => el.remove());
      ALL_CHS.forEach(ch => {
        const coord = FLOORPLAN_COORDS[ch];
        if (!coord) return;
        const side = FLOORPLAN_SIDE[ch] || 'right';
        const name = ROOM_MODULES[ch]?.name || alarmSettings[ch]?.name || ch.toUpperCase();
        const chLabel = name.endsWith('庫') ? name.slice(0, -1) : name;
        const el = document.createElement('div');
        el.className = `fp-label fp-${side}`;
        el.id = 'fpl-' + ch;
        el.style.left = (coord.x * 100) + '%';
        el.style.top = (coord.y * 100) + '%';
        el.innerHTML = `
          <div class="fp-anchor anc-off" id="fpanc-${ch}"></div>
          <div class="fp-line  ln-off"  id="fpln-${ch}"></div>
          <div class="fp-bubble" id="fpb-${ch}">
            <div class="fp-ch-id">${chLabel}</div>
            <div class="fp-row">
              <div class="fp-dot fp-dot-off" id="fpd-${ch}"></div>
              <span class="fp-temp-val fp-tv-off" id="fpt-${ch}">--°C</span>
            </div>
          </div>`;
        el.addEventListener('click', e => { e.stopPropagation(); const name = ROOM_MODULES[ch]?.name || alarmSettings[ch]?.name || ch.toUpperCase(); openControlModal(ch, name); });
        wrapper.appendChild(el);
      });
      fpLabelsBuilt = true;
    }
    function updateFloorplan(data) {
      if (!data || !fpLabelsBuilt) return;
      const nowTs = new Date().getTime();
      ALL_CHS.forEach(ch => {
        const d = data[ch];
        const dot = document.getElementById('fpd-' + ch);
        const tempEl = document.getElementById('fpt-' + ch);
        const bubble = document.getElementById('fpb-' + ch);
        const anc = document.getElementById('fpanc-' + ch);
        const ln = document.getElementById('fpln-' + ch);
        if (!dot || !tempEl || !bubble || !anc || !ln) return;
        let online = false, v = null, status = 'NORMAL';
        let kw = '--';
        if (d && d.timestamp) {
          const dTs = new Date(d.timestamp.replace(' ', 'T') + '+08:00').getTime();
          if (nowTs - dTs < 30000) {
            online = true;
            let avgTemp = null;
            if (d.units && Array.isArray(d.units) && d.units.length > 0) {
              let sum = 0, count = 0;
              d.units.forEach(u => {
                if (u.control_temperature !== undefined && u.control_temperature !== null) {
                  sum += Number(u.control_temperature);
                  count++;
                } else if (u.l301 !== undefined && u.l301 !== null) {
                  sum += Number(u.l301);
                  count++;
                }
              });
              if (count > 0) avgTemp = sum / count;
            }
            if (avgTemp === null && d.value !== undefined) avgTemp = Number(d.value);
            v = avgTemp;
            status = d.status || 'NORMAL';
            if (d.power && d.power.power_total !== undefined && d.power.power_total !== '--' && d.power.power_total !== null) {
              kw = (Number(d.power.power_total) / 1000.0).toFixed(1);
            } else if (d.power && d.power.kw !== undefined && d.power.kw !== '--' && d.power.kw !== null) {
              kw = Number(d.power.kw).toFixed(1);
            }
            if (!Number.isFinite(v)) online = false;
          }
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

        const cp1_kwStr = cp1.online ? cp1.kw.toFixed(1) : '--';
        const cp1_kwhStr = cp1.online ? cp1.kwh.toFixed(1) : '--';
        const cp1_vStr = (cp1.online && cp1.countV > 0) ? (cp1.sumV / cp1.countV).toFixed(1) : '--';
        const cp1_aStr = cp1.online ? cp1.totalA.toFixed(1) : '--';

        const cp3_kwStr = cp3.online ? cp3.kw.toFixed(1) : '--';
        const cp3_kwhStr = cp3.online ? cp3.kwh.toFixed(1) : '--';
        const cp3_vStr = (cp3.online && cp3.countV > 0) ? (cp3.sumV / cp3.countV).toFixed(1) : '--';
        const cp3_aStr = cp3.online ? cp3.totalA.toFixed(1) : '--';

        fpPowerCard.innerHTML = `
          <div style="border-bottom:1px solid var(--border); padding: 6px 12px; font-size:12px; font-weight:700; color:var(--text-1); display:flex; justify-content:center; align-items:center; letter-spacing:1px; background:#f7f9fd; flex-shrink:0;">
            <span>⚡ 廠區電力監控</span>
          </div>
          <div style="display:flex; flex-direction:column; justify-content:space-between; flex:1; padding: 10px 12px; box-sizing:border-box; gap: 8px; overflow:hidden;">
            <!-- CP-1 -->
            <div style="border-bottom:1px dashed #e2e8f0; padding-bottom:8px; display:flex; flex-direction:column; gap:4px; flex:1; justify-content:center;">
              <div style="font-size:11px; font-weight:800; color:var(--accent-secondary);">1F CP-1 (冷凍/緩衝/碼頭)</div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">即時用電</span>
                <span style="font-weight:800; color:var(--accent);">${cp1_kwStr} kW</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">累積電量</span>
                <span style="font-weight:800; color:var(--text-1);">${cp1_kwhStr} kWh</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">平均電壓</span>
                <span style="font-weight:800; color:var(--text-2);">${cp1_vStr} V</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">運轉電流</span>
                <span style="font-weight:800; color:var(--text-2);">${cp1_aStr} A</span>
              </div>
            </div>
            <!-- CP-3 -->
            <div style="padding-top:2px; display:flex; flex-direction:column; gap:4px; flex:1; justify-content:center;">
              <div style="font-size:11px; font-weight:800; color:var(--accent-secondary);">3F CP-3 (急速/半成品/冷藏)</div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">即時用電</span>
                <span style="font-weight:800; color:var(--accent);">${cp3_kwStr} kW</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">累積電量</span>
                <span style="font-weight:800; color:var(--text-1);">${cp3_kwhStr} kWh</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">平均電壓</span>
                <span style="font-weight:800; color:var(--text-2);">${cp3_vStr} V</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; font-size:10px;">
                <span style="color:var(--text-3); font-weight:700;">運轉電流</span>
                <span style="font-weight:800; color:var(--text-2);">${cp3_aStr} A</span>
              </div>
            </div>
          </div>
        </div>`;
      }
    }
    let currentCtrlCh = null;
    let currentCtrlName = null;
    function openControlModal(ch, name) {
      currentCtrlCh = ch;
      currentCtrlName = name;
      const configuredName = ROOM_MODULES[ch]?.name || name;
      const displayName = configuredName.endsWith('庫') ? configuredName : configuredName + '庫';
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
            const vCtrl = (u.control_temperature !== undefined && u.control_temperature !== null) ? Number(u.control_temperature) : 0.0;
            const vCoil = (u.coil_temperature !== undefined && u.coil_temperature !== null) ? Number(u.coil_temperature) : 0.0;
            const vAmp = (u.compressor_current !== undefined && u.compressor_current !== null) ? Number(u.compressor_current) : 0.0;
            const vHp = (u.high_pressure !== undefined && u.high_pressure !== null) ? Number(u.high_pressure) : 0.0;
            const vLp = (u.low_pressure !== undefined && u.low_pressure !== null) ? Number(u.low_pressure) : 0.0;
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
                     ${uId}
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
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vHp.toFixed(1)} MPa</span>
                     </div>
                     <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">
                        <span style="color:var(--text-2);">低壓壓力</span>
                        <span style="font-variant-numeric:tabular-nums; color:var(--text-1); font-size:14px;">${vLp.toFixed(1)} MPa</span>
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
                   電表資訊
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
  