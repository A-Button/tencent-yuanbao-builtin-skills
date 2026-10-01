#!/usr/bin/env node
/**
 * RollingGo 酒店连接器 API 调用工具 (免第三方依赖，纯 Node.js 标准库)
 * 供 Agent 在具备 Node.js 执行环境时直接调用
 */

import process from 'node:process';

const DEFAULT_BASE_URL = process.env.MCP_BASE_URL || 'https://mcp.rollinggo.cn/mcp';

/**
 * 获取默认 Bearer Token (读取环境变量 ACCESS_TOKEN / TOKEN / MCP_TOKEN)
 */
function getDefaultToken() {
  return process.env.ACCESS_TOKEN || process.env.TOKEN || process.env.MCP_TOKEN || '';
}

/**
 * 发起 API 请求
 */
async function requestApi(endpoint, method = 'POST', payload = null, token = null, baseUrl = null) {
  const base = (baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, '');
  const url = `${base}/${endpoint.replace(/^\/+/, '')}`;
  const reqToken = token || getDefaultToken();

  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'User-Agent': 'RollingGo-Agent-Skill/1.0',
  };

  if (reqToken) {
    headers['Authorization'] = `Bearer ${reqToken}`;
  }

  const options = {
    method: method.toUpperCase(),
    headers,
  };

  if (payload !== null && method.toUpperCase() === 'POST') {
    options.body = JSON.stringify(payload);
  }

  try {
    const res = await fetch(url, options);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch {
      return { success: false, code: res.status, message: `HTTP ${res.status}: ${text}` };
    }
  } catch (err) {
    return { success: false, code: 5000, message: err.message };
  }
}

/**
 * 命令行参数解析器 (免外部库)
 */
function parseArgv(argv) {
  const args = argv.slice(2);
  let command = null;
  const positional = [];
  const options = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
      continue;
    }
    if (!command && !arg.startsWith('-')) {
      command = arg;
      continue;
    }
    if (arg.startsWith('--')) {
      const eqIdx = arg.indexOf('=');
      let key, val;
      if (eqIdx !== -1) {
        key = arg.slice(2, eqIdx);
        val = arg.slice(eqIdx + 1);
      } else {
        key = arg.slice(2);
        if (i + 1 < args.length && !args[i + 1].startsWith('-')) {
          val = args[++i];
        } else {
          val = true;
        }
      }
      addOption(options, key, val);
    } else if (arg.startsWith('-')) {
      const key = arg.slice(1);
      let val;
      if (i + 1 < args.length && !args[i + 1].startsWith('-')) {
        val = args[++i];
      } else {
        val = true;
      }
      addOption(options, key, val);
    } else {
      positional.push(arg);
    }
  }

  return { command, options, positional };
}

function addOption(options, rawKey, val) {
  const camelKey = rawKey.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase());
  if (options[camelKey] !== undefined) {
    if (Array.isArray(options[camelKey])) {
      options[camelKey].push(val);
    } else {
      options[camelKey] = [options[camelKey], val];
    }
  } else {
    options[camelKey] = val;
  }
}

function printJson(data) {
  console.log(JSON.stringify(data, null, 2));
}

function printErrorAndExit(message, code = 4001) {
  printJson({ success: false, code, message });
  process.exit(1);
}

// ==================== 子命令实现 ====================

// 1. hotel-tags
async function cmdTags(options) {
  const token = options.token || options.t;
  const res = await requestApi('hoteltags', 'GET', null, token, options.baseUrl);
  printJson(res);
}

// 2. search-hotels
async function cmdSearch(options) {
  if (!options.originQuery || !options.place || !options.placeType) {
    printErrorAndExit('参数错误: 必须提供 --origin-query, --place 与 --place-type');
  }

  const validPlaceTypes = ['城市', '机场', '景点', '火车站', '地铁站', '酒店', '区/县', '详细地址'];
  if (!validPlaceTypes.includes(options.placeType)) {
    printErrorAndExit(`参数错误: --place-type 必须为以下之一: ${validPlaceTypes.join(', ')}`);
  }

  const payload = {
    originQuery: String(options.originQuery),
    place: String(options.place),
    placeType: String(options.placeType),
    size: options.size !== undefined ? parseInt(options.size, 10) : 5,
  };

  const checkIn = {};
  if (options.checkInDate) checkIn.checkInDate = String(options.checkInDate);
  if (options.stayNights !== undefined) checkIn.stayNights = parseInt(options.stayNights, 10);
  if (options.adultCount !== undefined) checkIn.adultCount = parseInt(options.adultCount, 10);
  if (Object.keys(checkIn).length > 0) {
    payload.checkInParam = checkIn;
  }

  const filterOpts = {};
  if (options.starRatings) {
    filterOpts.starRatings = String(options.starRatings).split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n));
  }
  const dist = options.distanceInMeter !== undefined ? options.distanceInMeter : options.distance;
  if (dist !== undefined) {
    filterOpts.distanceInMeter = parseInt(dist, 10);
  }
  if (Object.keys(filterOpts).length > 0) {
    payload.filterOptions = filterOpts;
  }

  const tags = {};
  const reqTagsRaw = options.requiredTags || options.requiredTag;
  if (reqTagsRaw) {
    const list = Array.isArray(reqTagsRaw) ? reqTagsRaw : String(reqTagsRaw).split(',');
    tags.requiredTags = list.map(t => String(t).trim()).filter(Boolean);
  }
  const prefBrandsRaw = options.preferredBrands || options.preferredBrand;
  if (prefBrandsRaw) {
    const list = Array.isArray(prefBrandsRaw) ? prefBrandsRaw : String(prefBrandsRaw).split(',');
    tags.preferredBrands = list.map(b => String(b).trim()).filter(Boolean);
  }
  const maxPrice = options.maxPricePerNight !== undefined ? options.maxPricePerNight : options.maxPrice;
  if (maxPrice !== undefined) {
    tags.maxPricePerNight = parseFloat(maxPrice);
  }
  if (Object.keys(tags).length > 0) {
    payload.hotelTags = tags;
  }

  const token = options.token || options.t;
  const res = await requestApi('hotelsearch', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 3. hotel-detail
async function cmdDetail(options) {
  if (!options.hotelId && !options.name) {
    printErrorAndExit('参数错误: 必须提供 --hotel-id 或 --name');
  }
  if (!options.checkInDate || !options.checkOutDate) {
    printErrorAndExit('参数错误: 必须提供 --check-in-date 和 --check-out-date');
  }

  const payload = {};
  if (options.hotelId) payload.hotelId = parseInt(options.hotelId, 10);
  if (options.name) payload.name = String(options.name);

  payload.dateParam = {
    checkInDate: String(options.checkInDate),
    checkOutDate: String(options.checkOutDate),
  };

  const occupancy = {
    roomCount: options.roomCount !== undefined ? parseInt(options.roomCount, 10) : 1,
    adultCount: options.adultCount !== undefined ? parseInt(options.adultCount, 10) : 2,
    childCount: options.childCount !== undefined ? parseInt(options.childCount, 10) : 0,
  };
  const childAgesRaw = options.childAges || options.childAge;
  if (childAgesRaw) {
    occupancy.childAgeDetails = String(childAgesRaw).split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n));
  }
  payload.occupancyParam = occupancy;

  const filterObj = {};
  if (options.cancelPolicy) filterObj.cancelPolicy = String(options.cancelPolicy);
  if (options.mealType) filterObj.mealType = String(options.mealType);
  if (Object.keys(filterObj).length > 0) {
    payload.filter = filterObj;
  }

  const token = options.token || options.t;
  const res = await requestApi('hoteldetail', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 4. price-confirm
async function cmdPriceConfirm(options) {
  if (!options.hotelId) printErrorAndExit('参数错误: 必须提供 --hotel-id');
  if (!options.ratePlanId) printErrorAndExit('参数错误: 必须提供 --rate-plan-id');
  if (!options.checkInDate || !options.checkOutDate) {
    printErrorAndExit('参数错误: 必须提供 --check-in-date 和 --check-out-date');
  }

  const rooms = parseInt(options.rooms || options.roomCount || 1, 10);
  const adults = parseInt(options.adults || options.adultCount || 2, 10);
  const children = parseInt(options.children || options.childCount || 0, 10);
  const childAgesRaw = options.childAges || options.childAge;
  const childAges = childAgesRaw
    ? String(childAgesRaw).split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
    : null;

  const occupancyDetails = [];
  for (let r = 1; r <= rooms; r++) {
    const item = {
      roomNum: r,
      adultCount: adults,
      childCount: children,
    };
    if (childAges) {
      item.childAgeDetails = childAges;
    }
    occupancyDetails.push(item);
  }

  // 注意：服务端字段严格区分大小写 hotelID 与 ratePlanID
  const payload = {
    hotelID: parseInt(options.hotelId, 10),
    ratePlanID: String(options.ratePlanId),
    numOfRooms: rooms,
    dateParam: {
      checkInDate: String(options.checkInDate),
      checkOutDate: String(options.checkOutDate),
    },
    occupancyDetails,
  };

  const token = options.token || options.t;
  const res = await requestApi('hotelpriceconfirm', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 5. book
async function cmdBook(options) {
  if (!options.referenceNo) printErrorAndExit('参数错误: 必须提供 --reference-no');
  if (!options.email) printErrorAndExit('参数错误: 必须提供联系邮箱 (--email)');

  const rawGuests = options.guests || options.guest;
  const guestList = [];

  if (rawGuests) {
    const entries = Array.isArray(rawGuests)
      ? rawGuests
      : String(rawGuests).split(';').map(s => s.trim()).filter(Boolean);

    for (const entry of entries) {
      const parts = entry.split(',').map(p => p.trim());
      const roomNum = parts.length > 0 && /^\d+$/.test(parts[0]) ? parseInt(parts[0], 10) : 1;
      const firstName = parts[1] || options.firstName || '';
      const lastName = parts[2] || options.lastName || '';
      const isAdult = parts[3] ? parts[3].toLowerCase() !== 'false' : true;
      const age = parts[4] && /^\d+$/.test(parts[4]) ? parseInt(parts[4], 10) : undefined;

      let roomEntry = guestList.find(r => r.roomNum === roomNum);
      if (!roomEntry) {
        roomEntry = { roomNum, guestInfo: [] };
        guestList.push(roomEntry);
      }

      const gInfo = { firstName, lastName, isAdult };
      if (age !== undefined) gInfo.age = age;
      roomEntry.guestInfo.push(gInfo);
    }
  } else {
    guestList.push({
      roomNum: 1,
      guestInfo: [
        {
          firstName: options.firstName || 'SAN',
          lastName: options.lastName || 'ZHANG',
          isAdult: true,
        },
      ],
    });
  }

  let contactFn = options.firstName;
  let contactLn = options.lastName;
  if ((!contactFn || !contactLn) && guestList.length > 0 && guestList[0].guestInfo.length > 0) {
    const firstG = guestList[0].guestInfo[0];
    contactFn = contactFn || firstG.firstName;
    contactLn = contactLn || firstG.lastName;
  }

  if (!contactFn || !contactLn) {
    printErrorAndExit('参数错误: 必须提供联系人姓名 (--first-name / --last-name) 或客人信息');
  }

  const payload = {
    referenceNo: String(options.referenceNo),
    contact: {
      firstName: contactFn,
      lastName: contactLn,
      email: String(options.email),
    },
    guestList,
  };

  const reqText = options.customerRequest || options.request;
  if (reqText) {
    payload.customerRequest = String(reqText);
  }

  const token = options.token || options.t;
  const res = await requestApi('hotelbook', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 6. orders
async function cmdOrders(options) {
  const status = options.status || options.s || 'ALL';
  const payload = { status };
  if (options.startDate && options.endDate) {
    payload.dateRange = {
      startDate: String(options.startDate),
      endDate: String(options.endDate),
    };
  }

  const token = options.token || options.t;
  const res = await requestApi('hotelorders', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 7. order-detail
async function cmdOrderDetail(options, positional) {
  const orderNo = options.orderNo || positional[0];
  if (!orderNo) {
    printErrorAndExit('参数错误: 必须提供订单号 (位置参数或 --order-no)');
  }
  const payload = { orderNo: String(orderNo) };
  const token = options.token || options.t;
  const res = await requestApi('hotelorderdetail', 'POST', payload, token, options.baseUrl);
  printJson(res);
}

// 帮助信息
function printHelp() {
  console.log(`
RollingGo 酒店 API 命令行代理工具 (纯标准库，Node.js 原生实现)

用法:
  node scripts/hotel.js <command> [options]

全局选项:
  --token, -t <token>     Bearer Access Token (缺省读取环境变量 ACCESS_TOKEN / TOKEN / MCP_TOKEN)
  --base-url <url>        API 服务地址 (默认: https://mcp.rollinggo.cn/mcp)
  --help, -h              显示帮助信息

子命令:
  hotel-tags              获取可用搜索标签字典
  search-hotels           搜索酒店列表
    --origin-query <str>  用户原始完整意图 (必填)
    --place <str>         地点名称 (必填，景点/车站/详细地址等须含城市前缀，如 杭州西湖)
    --place-type <str>    地点类型 (必填，城市/机场/景点/火车站/地铁站/酒店/区/县/详细地址)
    --size <n>            返回数量 (默认5)
    --check-in-date <d>   入住日期 YYYY-MM-DD
    --stay-nights <n>     入住晚数 (默认1)
    --adult-count <n>     成人数 (默认2)
    --star-ratings <m,n>  星级范围，如 4.0,5.0
    --distance-in-meter <m> 距离限制 (米)
    --required-tags <tag> 硬性标签 (逗号分隔)
    --preferred-brands <b> 偏好品牌 (逗号分隔)
    --max-price-per-night <p> 每晚最高预算
  hotel-detail            查询酒店房型报价与政策
    --hotel-id <id>       酒店ID (与 --name 二选一)
    --name <name>         酒店名称 (与 --hotel-id 二选一)
    --check-in-date <d>   入住日期 YYYY-MM-DD (必填)
    --check-out-date <d>  离店日期 YYYY-MM-DD (必填)
    --room-count <n>      房间数 (默认1)
    --adult-count <n>     成人数 (默认2)
    --child-count <n>     儿童数 (默认0)
    --child-ages <ages>   儿童年龄 (逗号分隔)
    --cancel-policy <p>   取消政策 (CANCELABLE / NON_CANCELABLE)
    --meal-type <m>       餐食类别 (WITH_BREAKFAST 等)
  price-confirm           锁定实时房型价格并换取 referenceNo
    --hotel-id <id>       酒店ID (必填)
    --rate-plan-id <id>   价格方案ID (必填)
    --rooms <n>           房间数 (默认1)
    --check-in-date <d>   入住日期 YYYY-MM-DD (必填)
    --check-out-date <d>  离店日期 YYYY-MM-DD (必填)
    --adults <n>          成人数 (默认2)
    --children <n>        儿童数 (默认0)
    --child-ages <ages>   儿童年龄 (逗号分隔)
  book                    提交预订并生成收银台支付链接
    --reference-no <no>   锁价凭证号 (必填)
    --first-name <str>    联系人名 (拼音)
    --last-name <str>     联系人姓 (拼音)
    --email <str>         联系邮箱 (必填)
    --guests <str>        客人列表: 房号,名,姓,是否成人[,年龄]
    --customer-request <s> 特殊要求备注
  orders                  查询订单列表
    --status, -s <status> 状态过滤 (ALL / PENDING / FINISHED，默认ALL)
    --start-date <d>      下单起始日期 YYYY-MM-DD
    --end-date <d>        下单结束日期 YYYY-MM-DD
  order-detail <orderNo>  查询单笔订单详情
    --order-no <no>       订单号 (也可直接作为位置参数传入)
`);
}

// 主入口
async function main() {
  const { command, options, positional } = parseArgv(process.argv);

  if (!command || options.help) {
    printHelp();
    process.exit(options.help ? 0 : 1);
  }

  switch (command) {
    case 'hotel-tags':
      await cmdTags(options);
      break;
    case 'search-hotels':
      await cmdSearch(options);
      break;
    case 'hotel-detail':
      await cmdDetail(options);
      break;
    case 'price-confirm':
      await cmdPriceConfirm(options);
      break;
    case 'book':
      await cmdBook(options);
      break;
    case 'orders':
      await cmdOrders(options);
      break;
    case 'order-detail':
      await cmdOrderDetail(options, positional);
      break;
    default:
      console.error(`未知子命令: ${command}`);
      printHelp();
      process.exit(1);
  }
}

main().catch(err => {
  printJson({ success: false, code: 5000, message: err.message });
  process.exit(1);
});
