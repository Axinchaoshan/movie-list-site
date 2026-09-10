// 极简评论区前端（原生 JS，无依赖）
// 用法：页面放 <section class="comments" data-page="影片id">…</section>，本脚本自动接管。
(function () {
  var box = document.querySelector(".comments");
  if (!box) return;
  var page = box.getAttribute("data-page") || "home";
  var listEl = box.querySelector("#c-list");
  var form = box.querySelector("#c-form");
  var nameEl = box.querySelector("#c-name");
  var textEl = box.querySelector("#c-content");
  var hpEl = box.querySelector("#c-hp");
  var countEl = box.querySelector(".c-count");
  var apiBase = "/api/comments";

  function fmt(ts) {
    var d = new Date(ts);
    var p = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return (
      d.getFullYear() +
      "-" +
      p(d.getMonth() + 1) +
      "-" +
      p(d.getDate()) +
      " " +
      p(d.getHours()) +
      ":" +
      p(d.getMinutes())
    );
  }

  function render(list) {
    listEl.textContent = "";
    if (!list.length) {
      var empty = document.createElement("p");
      empty.className = "c-empty";
      empty.textContent = "还没有评论，来抢沙发 🛋️";
      listEl.appendChild(empty);
      return;
    }
    list.forEach(function (c) {
      var item = document.createElement("div");
      item.className = "c-item";
      var head = document.createElement("div");
      head.className = "c-head";
      var name = document.createElement("span");
      name.className = "c-author";
      name.textContent = c.name || "匿名";
      var time = document.createElement("span");
      time.className = "c-time";
      time.textContent = fmt(c.created_at);
      head.appendChild(name);
      head.appendChild(time);
      var body = document.createElement("div");
      body.className = "c-body";
      body.textContent = c.content; // textContent 杜绝 XSS
      item.appendChild(head);
      item.appendChild(body);
      listEl.appendChild(item);
    });
  }

  function showNote(msg) {
    var old = box.querySelector(".c-note");
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var note = document.createElement("div");
    note.className = "c-note";
    note.textContent = msg;
    note.style.cssText =
      "margin-top:10px;padding:9px 12px;border-radius:9px;font-size:13px;" +
      "color:#7ee07e;background:rgba(126,224,126,.08);border:1px solid rgba(126,224,126,.25);";
    form.parentNode.insertBefore(note, form.nextSibling);
    setTimeout(function () {
      if (note.parentNode) note.parentNode.removeChild(note);
    }, 4500);
  }

  function load() {
    fetch(apiBase + "?page=" + encodeURIComponent(page))
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (Array.isArray(d)) {
          if (countEl) countEl.textContent = d.length;
          render(d);
        }
      })
      .catch(function () {
        if (countEl) countEl.textContent = "0";
      });
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      // 蜜罐：真人不会填这个隐藏框，填了就是机器人，直接忽略
      if (hpEl && hpEl.value) return;
      var content = (textEl.value || "").trim();
      if (!content) {
        textEl.focus();
        return;
      }
      var btn = form.querySelector(".c-submit");
      btn.disabled = true;
      btn.textContent = "发送中…";
      fetch(apiBase + "?page=" + encodeURIComponent(page), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: (nameEl.value || "").trim(),
          content: content,
        }),
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, j: j };
          });
        })
        .then(function (res) {
          if (res.ok && res.j && res.j.ok) {
            textEl.value = "";
            // 先审后发：刚发的评论进入待审，不会立刻显示在列表里
            showNote(
              res.j && res.j.pending
                ? "✅ 评论已提交，站长审核通过后会公开显示"
                : "✅ 评论已发布"
            );
          } else {
            alert(
              res.j && res.j.error ? "评论失败：" + res.j.error : "评论失败，请稍后再试"
            );
          }
          btn.disabled = false;
          btn.textContent = "发表评论";
        })
        .catch(function () {
          alert("网络错误，请稍后再试");
          btn.disabled = false;
          btn.textContent = "发表评论";
        });
    });
  }

  load();
})();
