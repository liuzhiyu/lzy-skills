// 低评论诊断器：判断「评论少」到底是真的（视频本就少评论）还是抓取脚本 bug。
// 用法：bsk navigate 到某视频详情页后，bsk evaluate --session <s> --timeout 60s "$(cat diag.js)"
// 返回 JSON：before/after 滚动前后条数、scFound（是否找到滚动容器）、
// hasMore（是否出现"暂时没有更多评论/暂无评论/全部评论"）、badge（评论数徽标）。
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const SEL_LIST = `[data-e2e="comment-list"]`;
  const SEL_ITEM = `[data-e2e="comment-item"]`;
  const q = s => document.querySelector(s);
  const getCount = () => { const l = q(SEL_LIST); return l ? l.querySelectorAll(SEL_ITEM).length : -1; };
  const url = location.href;
  let L = null, waited = 0;
  for (let i = 0; i < 40; i++) {
    L = q(SEL_LIST);
    if (L && L.querySelectorAll(SEL_ITEM).length > 0) break;
    await sleep(1000); waited++;
  }
  if (!L) return { ok: false, reason: "no_list", url };
  await sleep(3000);
  const before = getCount();
  const findScroller = () => {
    let el = q(SEL_LIST);
    while (el && el !== document.body) {
      const st = getComputedStyle(el);
      if ((/auto|scroll/.test(st.overflowY) || /auto|scroll/.test(st.overflowX)) && el.scrollHeight > el.clientHeight + 5) return el;
      el = el.parentElement;
    }
    el = q(SEL_LIST);
    while (el && el !== document.body) {
      const c = (el.className || "").toString();
      if (/scroll|comment|container|list/i.test(c) && el.scrollHeight > el.clientHeight + 5) return el;
      el = el.parentElement;
    }
    return null;
  };
  let sc = findScroller();
  for (let i = 0; i < 6; i++) {
    sc = sc || findScroller();
    if (sc) { try { sc.scrollTop = sc.scrollHeight; sc.scrollTop = sc.scrollHeight + 1200; sc.dispatchEvent(new Event("scroll")); } catch (e) {} }
    const list = q(SEL_LIST);
    if (list && list.scrollHeight > list.clientHeight + 5) { try { list.scrollTop = list.scrollHeight; list.dispatchEvent(new Event("scroll")); } catch (e) {} }
    try { window.scrollBy(0, 900); window.dispatchEvent(new Event("scroll")); } catch (e) {}
    await sleep(1000);
  }
  const after = getCount();
  const txt = (q(SEL_LIST).innerText || "").slice(0, 160);
  const badge = q(`[data-e2e="video-comment-count"]`);
  return {
    ok: true, url, before, after, scFound: !!sc,
    hasMoreText: /暂时没有更多评论|暂无评论|全部评论|没有更多/.test(txt),
    badge: badge ? badge.innerText.trim() : "",
    sampleText: txt
  };
})()
