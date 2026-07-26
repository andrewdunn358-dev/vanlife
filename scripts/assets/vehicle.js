(function () {
  var K = "vanlife.van";

  var CLASSES = {
    vw:         { label: "VW / small camper",    height: 2.0, length: 4.9, body: "panel_van",     sleeps: true,  caravan: false },
    panel:      { label: "Panel van conversion", height: 2.6, length: 5.9, body: "panel_van",     sleeps: true,  caravan: false },
    coachbuilt: { label: "Coachbuilt motorhome", height: 3.1, length: 7.0, body: "motor_caravan", sleeps: true,  caravan: false },
    aclass:     { label: "A-class motorhome",    height: 3.3, length: 8.0, body: "motor_caravan", sleeps: true,  caravan: false },
    caravan:    { label: "Touring caravan",      height: 2.6, length: 6.5, body: "caravan",       sleeps: true,  caravan: true  },
    twinaxle:   { label: "Twin axle caravan",    height: 2.7, length: 8.2, body: "caravan",       sleeps: true,  caravan: true  },
    car:        { label: "Car or estate",        height: 1.5, length: 4.8, body: "car",           sleeps: false, caravan: false }
  };

  var SC = {
    full:    { toilet: "fixed_cassette", grey: true,  black: true  },
    partial: { toilet: "portable",       grey: false, black: false },
    none:    { toilet: "none",           grey: false, black: false }
  };

  var v = null;
  try { var raw = localStorage.getItem(K); if (raw) v = JSON.parse(raw); } catch (e) {}
  function save() { try { localStorage.setItem(K, JSON.stringify(v)); } catch (e) {} }

  function article(label) {
    var l = label.toLowerCase();
    return (/^[aeiou]/.test(l) ? "an " : "a ") + l;
  }

  function selfContained() {
    var m = [];
    if (!v) return m;
    if (v.toilet === "none") m.push("no onboard toilet");
    else if (v.toilet === "portable") m.push("a portable toilet may not count as onboard");
    if (!v.grey) m.push("no sealed waste water tank");
    if (!v.black) m.push("no sealed sewage container");
    return m;
  }

  function verdict(rec) {
    var f = [];
    if (!v) return [["check", "Tell the site what you drive and this will say whether it applies to you."]];

    if (v.caravan && rec.excludes_caravans)
      f.push(["blocks", "Caravans are not accepted here."]);
    if (rec.max_height && v.height > rec.max_height)
      f.push(["blocks", "Around " + v.height + "m for " + article(v.label)
              + ", against a " + rec.max_height + "m limit here."]);
    if (rec.max_length && v.length > rec.max_length)
      f.push(["blocks", "Around " + v.length + "m long, against a " + rec.max_length + "m limit."]);

    if (rec.kind === "provision") {
      if (rec.self_contained) {
        var miss = selfContained();
        if (miss.length) f.push(["blocks", "Self-contained vehicles only: " + miss.join("; ") + "."]);
        else f.push(["ok", "Meets the self-contained requirement as you have described it."]);
      } else if (!f.length) {
        f.push(["ok", "No vehicle requirement recorded here."]);
      }
      return f;
    }

    if (rec.applies_to === "all_vehicles")
      f.push(["blocks", "Applies to every vehicle, whatever you drive."]);
    else if (rec.applies_to === "adapted_for_sleeping")
      f.push(v.sleeps
        ? ["blocks", "Applies to vehicles adapted for sleeping. Yours is, even though the V5C says "
            + v.body.replace(/_/g, " ") + "."]
        : ["ok", "Applies to vehicles adapted for sleeping. Yours is not."]);
    else if (rec.applies_to === "dvla_motor_caravan")
      f.push(v.body === "motor_caravan"
        ? ["blocks", "Applies to motor caravans, which yours is on the V5C."]
        : (v.sleeps
          ? ["check", "Written against the DVLA motor caravan class and your V5C says "
              + v.body.replace(/_/g, " ") + ". An officer may take a different view from the paperwork."]
          : ["ok", "Applies to motor caravans. Yours is not one."]));
    else if (!f.length)
      f.push(["check", "The recorded rule does not say which vehicles it covers."]);

    if (rec.restricts === "sleeping")
      f.push(["", "This restricts sleeping rather than parking, so leaving the vehicle here may be fine."]);
    return f;
  }

  function paint() {
    var slots = document.querySelectorAll("[data-rec]");
    slots.forEach(function (el) {
      var rec;
      try { rec = JSON.parse(el.getAttribute("data-rec")); } catch (e) { return; }
      var f = verdict(rec);
      var worst = f.some(function (x) { return x[0] === "blocks"; }) ? "blocks"
                : f.some(function (x) { return x[0] === "check"; }) ? "check" : "ok";
      var box = el.querySelector(".yours");
      if (!box) return;
      var label = { blocks: "Not for your van", check: "Worth checking",
                    ok: "Applies to your van" }[worst];
      box.className = "yours y-" + worst;
      box.innerHTML = "<b>" + label + "</b>" + f.map(function (x) { return x[1]; }).join(" ");
    });

    var sum = document.getElementById("v-summary");
    if (sum) {
      if (!v) sum.textContent = "";
      else if (!slots.length) sum.textContent = v.label + " saved. Every record on this site will now be checked against it.";
      else sum.textContent = document.querySelectorAll(".y-ok").length + " of "
             + slots.length + " records here apply to " + article(v.label) + ".";
    }

    var strip = document.getElementById("vstrip");
    if (strip) {
      var home = strip.getAttribute("data-home");
      strip.innerHTML = v
        ? "Checked against a <b>" + v.label.toLowerCase() + "</b>"
          + (v.sc === "full" ? ", fixed toilet and sealed tanks"
             : v.sc === "partial" ? ", portable toilet" : "")
          + ' &middot; <a href="' + home + '">change</a>'
        : '<a href="' + home + '">Tell the site what you drive</a>'
          + " and every record below will say whether it applies to you.";
    }
  }

  function markCards(key) {
    document.querySelectorAll(".vcard").forEach(function (b) {
      var on = b.getAttribute("data-v") === key;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-checked", on ? "true" : "false");
    });
    var fu = document.getElementById("vfollow");
    if (fu) fu.hidden = (key === "car");
  }

  function selectClass(key) {
    var c = CLASSES[key];
    if (!c) return;
    v = v || {};
    v.cls = key; v.label = c.label; v.height = c.height; v.length = c.length;
    v.body = c.body; v.sleeps = c.sleeps; v.caravan = c.caravan;
    if (key === "car") { v.sc = "none"; v.toilet = SC.none.toilet; v.grey = false; v.black = false; }
    save(); markCards(key); paint();
  }

  function selectSC(key) {
    if (!v) return;
    v.sc = key; v.toilet = SC[key].toilet; v.grey = SC[key].grey; v.black = SC[key].black;
    save();
    document.querySelectorAll(".vopt").forEach(function (b) {
      b.classList.toggle("is-on", b.getAttribute("data-sc") === key);
    });
    paint();
  }

  document.querySelectorAll(".vcard").forEach(function (b) {
    b.addEventListener("click", function () { selectClass(b.getAttribute("data-v")); });
  });
  document.querySelectorAll(".vopt").forEach(function (b) {
    b.addEventListener("click", function () { selectSC(b.getAttribute("data-sc")); });
  });

  if (v && v.cls) {
    markCards(v.cls);
    if (v.sc) document.querySelectorAll(".vopt").forEach(function (b) {
      b.classList.toggle("is-on", b.getAttribute("data-sc") === v.sc);
    });
  }
  paint();
})();
