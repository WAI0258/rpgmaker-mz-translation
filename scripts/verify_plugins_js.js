// 校验 RPG Maker MV/MZ 的 js/plugins.js：
//   1) 语法可解析
//   2) 参数值是否全为字符串（__collapsed 折叠标记豁免）
//   3) 复刻插件参数解析器（cast/predict），确认不会再抛 param.match is not a function
//   4) 与原版备份做结构比对（只比类型与数组长度，不比文本）
//
// 用法：
//   node verify_plugins_js.js --plugins <js/plugins.js> [--backup <原版 backup>]
// 退出码 0 = 全部通过。

const fs = require('fs');
const path = require('path');

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}

const PJ = arg('plugins', path.join('js', 'plugins.js'));
const BK = arg('backup', null);

const info = [];
const fail = [];
const ok = (m) => info.push('  [OK]   ' + m);
const bad = (m) => { fail.push(m); info.push('  [FAIL] ' + m); };

let plugins;
try {
  const text = fs.readFileSync(PJ, 'utf8');
  info.push('文件: ' + PJ);
  info.push('体积: ' + text.length.toLocaleString() + ' B');
  // 与 RPG Maker 相同的求值方式
  plugins = new Function(text + '\nreturn $plugins;')();
  ok('语法可解析，插件数 = ' + plugins.length);
} catch (e) {
  bad('解析失败: ' + e.message);
  console.log(info.join('\n'));
  process.exit(1);
}

// ---- 1) 参数值必须是字符串 ----
const NON_STR_ALLOWED = new Set(['__collapsed']);
const nonStr = [];
let biggest = 0;
for (const p of plugins) {
  for (const [k, v] of Object.entries(p.parameters || {})) {
    if (NON_STR_ALLOWED.has(k)) continue;
    if (typeof v !== 'string') {
      nonStr.push(p.name + '.' + k + ' -> ' + (Array.isArray(v) ? 'array' : typeof v));
    } else if (v.length > biggest) biggest = v.length;
  }
}
nonStr.length === 0
  ? ok('参数值全为字符串（最大单个参数 ' + biggest.toLocaleString() + ' B）')
  : nonStr.slice(0, 20).forEach(x => bad('参数值非字符串: ' + x));

// ---- 2) 复刻插件的类型转换 ----
function cast(param, type) {
  if (type === 'number') {
    if (typeof param !== 'string') {
      throw new Error('param.match is not a function（收到 ' + typeof param + '）');
    }
    return /^\-?\d+\.\d+$/.test(param) ? parseFloat(param) : parseInt(param);
  }
  if (type === 'boolean') return param === 'true';
  if (type === 'string') return param;
  throw new Error('Unknow type: ' + type);
}
function predict(param) {
  if (typeof param !== 'string') {
    throw new Error('param.match is not a function（predict 收到 ' + typeof param + '）');
  }
  if (/^\-?\d+$/.test(param) || /^\-?\d+\.\d+$/.test(param)) return 'number';
  if (param === 'true' || param === 'false') return 'boolean';
  return 'string';
}

// 常见被声明为数值/布尔的键名
const NUMKEYS = new Set(['VariableId', 'IconIndex', 'Priority', 'CommonEventId',
  'QuestOrderCommonEventId', 'ActorId', 'Opacity', 'X', 'Y', 'ScaleX', 'ScaleY',
  'Id', 'SwitchId', 'Width', 'Height', 'ItemId', 'ItemCount', 'GoldValue',
  'ExpValue', 'Volume', 'Pitch', 'Pan', 'Index', 'stateId', 'Value', 'CommandId',
  'FocusWindowIndex', 'Align', 'VisibleSwitchId', 'EnableSwitchId', 'RowNumber',
  'ColumnNumber', 'ItemHeight']);

const crashes = [];
let checked = 0;
function probe(obj, where) {
  if (Array.isArray(obj)) return obj.forEach(o => probe(o, where));
  if (!obj || typeof obj !== 'object') return;
  for (const [k, v] of Object.entries(obj)) {
    if (NUMKEYS.has(k)) {
      checked++;
      try { cast(v, 'number'); } catch (e) { crashes.push(where + ' 键=' + k + ' -> ' + e.message); }
    } else if (typeof v === 'string' && v.trim() && !'[{'.includes(v.trim()[0])) {
      try { predict(v); } catch (e) { crashes.push(where + ' 键=' + k + ' -> ' + e.message); }
    }
    if (typeof v === 'string' && /^\s*[[{]/.test(v)) {
      try { probe(JSON.parse(v), where); } catch (e) { /* 不是 JSON，跳过 */ }
    } else if (typeof v === 'object') {
      probe(v, where);
    }
  }
}
for (const p of plugins) {
  for (const [k, v] of Object.entries(p.parameters || {})) {
    if (typeof v === 'string' && /^\s*[[{]/.test(v)) {
      try { probe(JSON.parse(v), p.name + '.' + k); } catch (e) { /* 跳过 */ }
    }
  }
}
crashes.length === 0
  ? ok('复刻 cast()/predict() 抽查 ' + checked + ' 个参数值，无 param.match 异常')
  : crashes.slice(0, 20).forEach(x => bad('param.match 异常: ' + x));

// ---- 3) 与原版结构比对 ----
function deep(v, d) {
  if (d > 8 || typeof v !== 'string') return v;
  const s = v.trim();
  if ('[{'.includes(s[0]) && ']}'.includes(s[s.length - 1])) {
    try { return deep(JSON.parse(s), d + 1); } catch (e) { return v; }
  }
  return v;
}
function diff(c, b, where, out) {
  if (out.length > 300) return;
  const cArr = Array.isArray(c), bArr = Array.isArray(b);
  if (typeof c !== typeof b || cArr !== bArr || (c === null) !== (b === null)) {
    out.push(where + ': ' + typeof b + (bArr ? '[]' : '') + ' -> ' + typeof c + (cArr ? '[]' : ''));
    return;
  }
  if (cArr) {
    if (c.length !== b.length) out.push(where + ': 长度 ' + b.length + ' -> ' + c.length);
    for (let i = 0; i < Math.min(c.length, b.length); i++) diff(c[i], b[i], where + '[' + i + ']', out);
  } else if (c && typeof c === 'object') {
    for (const k of new Set([...Object.keys(c), ...Object.keys(b)])) {
      if (!(k in b)) out.push(where + '.' + k + ': 新增');
      else if (!(k in c)) out.push(where + '.' + k + ': 丢失');
      else diff(c[k], b[k], where + '.' + k, out);
    }
  }
}

if (BK && fs.existsSync(BK)) {
  try {
    const bak = new Function(fs.readFileSync(BK, 'utf8') + '\nreturn $plugins;')();
    const bmap = new Map(bak.map(p => [p.name, p]));
    const out = [];
    for (const p of plugins) {
      const b = bmap.get(p.name);
      if (!b) { out.push(p.name + ': 原版没有该插件'); continue; }
      const cp = p.parameters || {}, bp = b.parameters || {};
      for (const k of new Set([...Object.keys(cp), ...Object.keys(bp)])) {
        if (!(k in bp)) out.push(p.name + '.' + k + ': 新增参数');
        else if (!(k in cp)) out.push(p.name + '.' + k + ': 丢失参数');
        else diff(deep(cp[k], 0), deep(bp[k], 0), p.name + '.' + k, out);
      }
    }
    out.length === 0
      ? ok('与原版结构差异 = 0')
      : out.slice(0, 20).forEach(x => bad('结构差异: ' + x));
  } catch (e) {
    info.push('  [SKIP] 原版备份无法解析: ' + e.message);
  }
} else {
  info.push('  [SKIP] 未提供 --backup，跳过结构比对');
}

console.log(info.join('\n'));
console.log(fail.length === 0 ? '\nRESULT: OK' : '\nRESULT: FAIL (' + fail.length + ')');
process.exit(fail.length === 0 ? 0 : 1);
