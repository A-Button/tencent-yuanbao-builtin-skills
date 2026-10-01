# 塔罗静态产物状态实验

本页描述当前候选版已实现的 HTML 状态协议；宿主自带分享是否采集／回填快照仍取决于产品接入。每次生成塔罗 HTML 时，配置写入一个随机 `artifactId`，与这份文件一起固定。页面把牌组顺序、正逆位和已选牌索引存入当前浏览器的 `localStorage`，key 为 `yuanbao:tarot:state:v1:<artifactId>`。刷新或重开同一产物时，恢复到已翻开的稳定牌面；动画进行中刷新，也恢复已选的牌。用户点「再抽一次」或「重新洗牌」时清除上一局并开始新局。存储不可用时页面仍可抽牌，只是不承诺刷新恢复。

## 宿主分享接入

页面内「分享结果图片」生成并在分享弹窗展示 PNG，由用户长按保存或分享。产品层若要分享可交互 HTML 的当前结果，应在分享文件卡片时读取结果快照，并与原 `ResourceUrl` 一起下发。`ResourceUrl` 的 `resourceId` 定位原始 HTML；快照定位分享时的三张牌。

嵌入页面的宿主可向 iframe 发送：

```js
iframe.contentWindow.postMessage({
  type: 'tarot:request-share-snapshot', requestId: '本次请求的唯一标识'
}, iframeOrigin);
```

页面向父窗口回传 `type: 'tarot:share-snapshot'`、同一个 `requestId` 和 `snapshot`。只有三张牌全部完成时 `snapshot` 才是对象，否则为 `null`。对象形如：

```json
{"v":1,"kind":"tarot-result","artifactId":"...","cards":[{"id":"...","reversed":false},{"id":"...","reversed":true},{"id":"...","reversed":false}]}
```

宿主需要把这份快照作为分享消息元数据保存，或把 JSON 的 UTF-8 字节编码为 base64url，附在固定的 `ResourceUrl` 后面作为 `#tarot-state=<base64url>`。接收者的页面会优先读取有效片段，并直接显示同一结果。宿主若单独保存元数据，也可在 iframe 加载后发送 `{type:'tarot:open-share-snapshot',snapshot}`。页面只接受父窗口的消息，并核对版本、产物 ID、牌 ID 和正逆位。分享快照不会覆盖接收者本地的旧牌局；接收者点重新抽牌后才开始自己的牌局。

**产品侧仍需接入的环节**：在发起会话分享时请求快照、存入分享消息，并在接收者打开时附加 URL 片段或发送消息。仅转发原 `ResourceUrl` 不会携带用户抽牌后的状态。CDN 预签名直链有有效期，不能作为快照链接的长期基址；应使用固定的 `ResourceUrl`。如果下载跳转或 WebView 丢弃 URL 片段，应使用消息元数据回填方案。

现有 `.html` 下载还受 Referer 灰度校验。分享入口应从产品认可的同 host 页面打开，并在真实分享链路确认接收者能拿到 HTML；该检查与页面内状态恢复是两个独立条件。

## 验证范围

本地可验证状态序列化、恢复、产物隔离、快照编码与单文件打包。真实端上的刷新恢复还取决于同一产物再次打开时的浏览器存储空间与 origin；会话分享端到端还取决于上述宿主接入。
