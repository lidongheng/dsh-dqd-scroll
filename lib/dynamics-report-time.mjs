const shanghaiTimestamp = (value) => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(value).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
};

export function rollingReportRange(now) {
  return {
    since: shanghaiTimestamp(new Date(now.getTime() - 24 * 60 * 60 * 1000)),
    until: shanghaiTimestamp(now),
  };
}

export function validateManualRange(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error('请提供自定义开始时间和结束时间。');
  }
  for (const [label, value] of [['开始', body.since], ['结束', body.until]]) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value) || value.startsWith('0000-')) {
      throw new Error(`${label}时间必须精确到分钟，格式为 YYYY-MM-DDTHH:mm。`);
    }
    // UTC 仅用于校验日历日期，提交值始终按上海本地时间原样传递。
    const parsed = new Date(`${value}:00Z`);
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 16) !== value) {
      throw new Error(`${label}时间不是有效的日期时间。`);
    }
  }
  if (body.since >= body.until) throw new Error('开始时间必须早于结束时间。');
  return { since: body.since, until: body.until };
}
