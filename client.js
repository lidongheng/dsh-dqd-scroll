window.__ModuleLoader__.load({
  id: 'dsh-dqd-scroll',
  factory: (require) => {
    const React = require('react');
    const h = React.createElement;
    const API = '/api/dqd-scroll';

    const request = async (path, options) => {
      const response = await fetch(`${API}${path}`, {
        credentials: 'same-origin',
        ...options,
      });
      let body;
      try {
        body = await response.json();
      } catch {
        throw new Error(`HTTP ${response.status}：服务没有返回 JSON。`);
      }
      if (!response.ok || body.ok === false) {
        const error = new Error(body.error || `HTTP ${response.status}`);
        error.payload = body;
        throw error;
      }
      return body;
    };

    const getSettings = () => request('/settings');
    const getLogs = () => request('/logs');
    const saveSettings = (settings) => request('/settings', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(settings),
    });
    const installPythonEnvironment = () => request('/python-environment/install', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({}),
    });
    const CSS = `
[data-dqd-page]{display:flex;flex-direction:column;gap:18px;max-width:720px;padding:4px 2px 10px;}
[data-dqd-title]{font-size:18px;font-weight:600;margin:0;}
[data-dqd-note]{font-size:12px;line-height:18px;color:var(--dsw-alias-label-tertiary,#8b9199);}
[data-dqd-section]{display:flex;flex-direction:column;gap:9px;padding:14px;border:1px solid var(--dsw-alias-bg-layer-3,rgba(127,127,127,.2));border-radius:12px;}
[data-dqd-section-title]{font-size:14px;font-weight:600;margin:0;}
[data-dqd-label]{font-size:13px;font-weight:500;}
[data-dqd-input],[data-dqd-textarea]{box-sizing:border-box;width:100%;padding:8px 10px;border:1px solid var(--dsw-alias-bg-layer-3,rgba(127,127,127,.24));border-radius:8px;background:var(--dsw-alias-bg-layer-4,rgba(127,127,127,.1));color:inherit;font:inherit;font-size:13px;}
[data-dqd-input]:focus,[data-dqd-textarea]:focus{outline:none;border-color:var(--dsw-alias-brand-primary,#3b82f6);}
[data-dqd-textarea]{min-height:132px;resize:vertical;line-height:1.6;}
[data-dqd-row]{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
[data-dqd-button]{align-self:flex-start;padding:8px 13px;border:1px solid var(--dsw-alias-bg-layer-3,rgba(127,127,127,.24));border-radius:8px;background:var(--dsw-alias-bg-layer-4,rgba(127,127,127,.12));color:inherit;font:inherit;font-size:13px;cursor:pointer;}
[data-dqd-button][data-primary]{border-color:#3b82f6;background:#3b82f6;color:#fff;}
[data-dqd-button]:disabled{opacity:.5;cursor:default;}
[data-dqd-message]{font-size:12px;line-height:18px;white-space:pre-wrap;word-break:break-word;}
[data-dqd-message][data-error]{color:#e06c75;}
[data-dqd-message][data-success]{color:#37a76f;}
[data-dqd-output]{max-height:240px;overflow:auto;margin:0;padding:10px;border-radius:8px;background:var(--dsw-alias-bg-layer-4,rgba(0,0,0,.2));font-size:11px;line-height:16px;white-space:pre-wrap;word-break:break-word;}
`;

    function Panel() {
      const [settings, setSettings] = React.useState(null);
      const [pythonEnvironment, setPythonEnvironment] = React.useState(null);
      const [availableTeamNames, setAvailableTeamNames] = React.useState([]);
      const [dailyRunTime, setDailyRunTime] = React.useState(null);
      const [executionMethod, setExecutionMethod] = React.useState(null);
      const [teamNamesText, setTeamNamesText] = React.useState(null);
      const [interestsText, setInterestsText] = React.useState(null);
      const [scheduleState, setScheduleState] = React.useState(null);
      const [logText, setLogText] = React.useState('');
      const [logPath, setLogPath] = React.useState('');
      const [loadingError, setLoadingError] = React.useState('');
      const [message, setMessage] = React.useState('');
      const [messageTone, setMessageTone] = React.useState('');
      const [busy, setBusy] = React.useState('');

      React.useEffect(() => {
        let active = true;
        getSettings().then((response) => {
          if (!active) return;
          setSettings(response.settings);
          setPythonEnvironment(response.pythonEnvironment);
          setAvailableTeamNames(response.availableTeamNames);
          setDailyRunTime(response.settings.dailyRunTime);
          setExecutionMethod(response.settings.executionMethod);
          setTeamNamesText(response.settings.teamNames.join('\n'));
          setInterestsText(response.settings.interests.join('\n'));
          setScheduleState(response.scheduleState);
          setLogPath(response.logPath);
          getLogs().then((logResponse) => {
            if (!active) return;
            setLogText(logResponse.log);
          }).catch((error) => {
            if (active) setLoadingError(error.message);
          });
        }).catch((error) => {
          if (active) setLoadingError(error.message);
        });
        return () => {
          active = false;
        };
      }, []);

      const showMessage = (text, tone) => {
        setMessage(text);
        setMessageTone(tone);
      };

      const refreshLogs = async () => {
        try {
          const [settingsResponse, logResponse] = await Promise.all([getSettings(), getLogs()]);
          setScheduleState(settingsResponse.scheduleState);
          setLogText(logResponse.log);
          setLogPath(logResponse.logPath);
        } catch (error) {
          showMessage(error.message, 'error');
        }
      };

      const scheduleSummary = () => {
        if (!scheduleState) return '任务状态尚未同步。';
        if (!scheduleState.registered) {
          if (scheduleState.error) return `自动调度未启用：${scheduleState.error}`;
          return '自动调度未启用。';
        }
        let schedulerName = '自动调度';
        if (scheduleState.scheduler === 'windows-task-scheduler') schedulerName = 'Windows 任务计划';
        if (scheduleState.scheduler === 'plugin-interval') schedulerName = 'DSH 插件定时器';
        if (!scheduleState.last_status) return `${schedulerName}已启用：${scheduleState.daily_run_time}，${scheduleState.execution_method}。`;
        return `${schedulerName}已启用：${scheduleState.daily_run_time}，${scheduleState.execution_method}；上次执行状态：${scheduleState.last_status}。`;
      };

      const onSave = async () => {
        if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(dailyRunTime)) {
          showMessage('请输入 00:00 至 23:59 之间的运行时间。', 'error');
          return;
        }

        const interests = interestsText
          .split(/\r?\n/)
          .map((interest) => interest.trim())
          .filter((interest) => interest.length > 0);
        const teamNames = teamNamesText
          .split(/\r?\n/)
          .map((teamName) => teamName.trim())
          .filter((teamName) => teamName.length > 0);
        if (teamNames.length === 0) {
          showMessage('请至少填写一个关注球队名称。', 'error');
          return;
        }
        if (new Set(teamNames).size !== teamNames.length) {
          showMessage('关注球队名称不能重复。', 'error');
          return;
        }
        setBusy('save');
        showMessage('', '');
        try {
          const response = await saveSettings({ dailyRunTime, executionMethod, teamNames, interests });
          setSettings(response.settings);
          setDailyRunTime(response.settings.dailyRunTime);
          setExecutionMethod(response.settings.executionMethod);
          setTeamNamesText(response.settings.teamNames.join('\n'));
          setInterestsText(response.settings.interests.join('\n'));
          setScheduleState(response.scheduleState);
          await refreshLogs();
          if (response.scheduleState.registered) {
            showMessage('设置已保存，自动调度已更新。', 'success');
          } else {
            showMessage(`设置已保存，但自动调度未启用：${response.scheduleState.error}`, 'error');
          }
        } catch (error) {
          showMessage(error.message, 'error');
        } finally {
          setBusy('');
        }
      };

      const onInstallPythonEnvironment = async () => {
        setBusy('python-environment');
        showMessage('正在准备 uv、Python 3.11 和本机球队数据库，请保持 DSH 运行。', '');
        try {
          const response = await installPythonEnvironment();
          setPythonEnvironment(response.pythonEnvironment);
          setScheduleState(response.scheduleState);
          await refreshLogs();
          if (response.scheduleState.registered) {
            showMessage(`${response.pythonEnvironment.output}\n自动调度已启用。`, 'success');
          } else {
            showMessage(`${response.pythonEnvironment.output}\n自动调度未启用：${response.scheduleState.error}`, 'error');
          }
        } catch (error) {
          showMessage(error.message, 'error');
        } finally {
          setBusy('');
        }
      };

      let settingsContent;
      if (settings === null) {
        const loadingText = loadingError || '正在读取项目配置…';
        settingsContent = h('div', { 'data-dqd-note': '' }, loadingText);
      } else {
        settingsContent = h('div', { 'data-dqd-section': '' },
          h('h2', { 'data-dqd-section-title': '' }, '自动动态日报'),
          h('label', { 'data-dqd-label': '', htmlFor: 'dqd-scroll-daily-run-time' }, '每天运行时间'),
          h('input', {
            id: 'dqd-scroll-daily-run-time',
            'data-dqd-input': '',
            type: 'time',
            value: dailyRunTime,
            onChange: (event) => setDailyRunTime(event.target.value),
          }),
          h('label', { 'data-dqd-label': '', htmlFor: 'dqd-scroll-execution-method' }, '执行方式'),
          h('select', {
            id: 'dqd-scroll-execution-method',
            'data-dqd-input': '',
            value: executionMethod,
            onChange: (event) => setExecutionMethod(event.target.value),
          },
          h('option', { value: 'command' }, '命令启动（当前方式）'),
          h('option', { value: 'model' }, '模型执行（headless DSH，按 duty.md 执行）')),
          h('div', { 'data-dqd-note': '' }, `Windows 使用系统任务计划，macOS 使用 DSH 插件定时器；均按 Asia/Shanghai 每天执行。macOS 需保持 DSH 运行且电脑唤醒，Windows 需电脑唤醒且用户保持登录。模型方式使用保存设置时读取到的 DSH 当前模型，修改模型后请重新保存设置。关注内容留空或 Python 环境未安装时不会启用调度。可选球队：${availableTeamNames.join('、')}`),
          h('div', { 'data-dqd-note': '' }, scheduleSummary()),
          h('label', { 'data-dqd-label': '', htmlFor: 'dqd-scroll-team-names' }, '关注球队（每行一个懂球帝球队名称）'),
          h('textarea', {
            id: 'dqd-scroll-team-names',
            'data-dqd-textarea': '',
            value: teamNamesText,
            onChange: (event) => setTeamNamesText(event.target.value),
            placeholder: '曼城',
          }),
          h('label', { 'data-dqd-label': '', htmlFor: 'dqd-scroll-interests' }, '关注内容（每行一条）'),
          h('textarea', {
            id: 'dqd-scroll-interests',
            'data-dqd-textarea': '',
            value: interestsText,
            onChange: (event) => setInterestsText(event.target.value),
            placeholder: '每行填写一个关注主题',
          }),
          h('div', { 'data-dqd-row': '' },
            h('button', {
              'data-dqd-button': '',
              'data-primary': '',
              disabled: Boolean(busy),
              onClick: onSave,
            }, busy === 'save' ? '保存中…' : '保存设置')),
        );
      }

      return h('div', { 'data-dqd-page': '' },
        h('h1', { 'data-dqd-title': '' }, '懂球帝动态日报'),
        settingsContent,
        pythonEnvironment === null ? null : h('div', { 'data-dqd-section': '' },
          h('h2', { 'data-dqd-section-title': '' }, '本机运行环境'),
          h('div', { 'data-dqd-note': '' }, pythonEnvironment.ready
            ? `Python ${pythonEnvironment.pythonVersion} 已就绪：${pythonEnvironment.pythonPath}`
            : '尚未初始化。首次安装会在 DSH 用户数据目录准备 uv 与 Python 3.11，并初始化球队数据库；无需预装 Python。'),
          h('div', { 'data-dqd-note': '' }, '安装需要网络连接以取得经过 SHA-256 校验的运行环境。配置、数据库、运行状态和日报都保存在本机 DSH 用户数据目录。'),
          h('button', {
            'data-dqd-button': '',
            'data-primary': '',
            disabled: Boolean(busy),
            onClick: onInstallPythonEnvironment,
          }, busy === 'python-environment' ? '安装和初始化中…' : '准备运行环境')),
        h('div', { 'data-dqd-section': '' },
          h('h2', { 'data-dqd-section-title': '' }, '运行日志'),
          h('div', { 'data-dqd-note': '' }, logPath),
          h('div', { 'data-dqd-row': '' },
            h('button', { 'data-dqd-button': '', onClick: refreshLogs }, '刷新日志')),
          h('pre', { 'data-dqd-output': '' }, logText || '暂无运行日志。')),
        message ? h('div', {
          'data-dqd-message': '',
          ...(messageTone ? { [`data-${messageTone}`]: '' } : {}),
        }, message) : null,
      );
    }

    return {
      inject: ['slots'],
      apply(context) {
        const slots = (typeof context.get === 'function' ? context.get('slots') : undefined) || context.slots;
        if (!slots) return;

        const style = document.createElement('style');
        style.setAttribute('data-plugin-css', 'dsh-dqd-scroll');
        style.textContent = CSS;
        document.head.appendChild(style);
        context.effect(() => () => style.remove(), 'dsh-dqd-scroll: 设置页样式');

        slots.inject('settings.section', () => slots.register(
          { name: 'settings.section', id: 'dqd-scroll', order: 31, label: '刷懂球帝' },
          () => h(Panel),
        ));
      },
    };
  },
});
