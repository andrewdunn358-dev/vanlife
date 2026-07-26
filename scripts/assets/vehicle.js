(function () {
  var K = "vanlife.vehicle";
  var d = { height: 2.6, length: 5.4, body: "panel_van", sleeps: true,
            toilet: "none", grey: false, black: false };
  try { var st = localStorage.getItem(K); if (st) d = JSON.parse(st); } catch (e) {}

  function selfContained(v) {
    var m = [];
    if (v.toilet === "none") m.push("no onboard toilet");
    else if (v.toilet === "portable") m.push("a portable toilet may not count as onboard");
    if (!v.grey) m.push("no sealed waste water tank");
    if (!v.black) m.push("no sealed sewage container");
    return m;
  }

  function verdict(rec, v) {
    var f = [];
    if (rec.max_height && v.height > rec.max_height) {
      f.push(["blocks", "Your " + v.height + "m exceeds the " + rec.max_height + "m limit here."]);
    }

    if (rec.kind === "provision") {
      if (rec.self_contained) {
        var miss = selfContained(v);
        if (miss.length) f.push(["blocks", "Self-contained vehicles only: " + miss.join("; ") + "."]);
        else f.push(["ok", "Meets the self-contained requirement as you have described the van."]);
      } else if (!f.length) {
        f.push(["ok", "No vehicle requirement recorded for this one."]);
      }
      return f;
    }

    if (rec.restricts === "parking" && !rec.applies_to) {
      f.push(["check", "Restricts parking rather than sleeping. Applies to you if you leave the vehicle here."]);
      return f;
    }

    if (rec.applies_to === "all_vehicles") {
      f.push(["blocks", "Applies to every vehicle, whatever you drive."]);
    } else if (rec.applies_to === "adapted_for_sleeping") {
      f.push(v.sleeps
        ? ["blocks", "Applies to vehicles adapted for sleeping. Yours is, even though the V5C says "
            + v.body.replace(/_/g, " ") + "."]
        : ["ok", "Applies to vehicles adapted for sleeping. Yours is not."]);
    } else if (rec.applies_to === "dvla_motor_caravan") {
      f.push(v.body === "motor_caravan"
        ? ["blocks", "Applies to motor caravans, which yours is on the V5C."]
        : (v.sleeps
          ? ["check", "Written against the DVLA motor caravan class, and your V5C says "
              + v.body.replace(/_/g, " ") + ". An enforcement officer may take a different view from the paperwork."]
          : ["ok", "Applies to motor caravans. Yours is not one."]));
    } else {
      f.push(["check", "The recorded rule does not make clear which vehicles it covers."]);
    }

    if (rec.restricts === "sleeping" && rec.kind === "restriction") {
      f.push(["", "Note this restricts sleeping, not parking. Leaving the vehicle here may be fine."]);
    }
    return f;
  }

  function apply() {
    document.querySelectorAll("[data-rec]").forEach(function (el) {
      var rec;
      try { rec = JSON.parse(el.getAttribute("data-rec")); } catch (e) { return; }
      var f = verdict(rec, d);
      var worst = f.some(function (x) { return x[0] === "blocks"; }) ? "blocks"
                : f.some(function (x) { return x[0] === "check"; }) ? "check" : "ok";
      var box = el.querySelector(".yours");
      if (!box) return;
      var label = { blocks: "Not for your van", check: "Worth checking",
                    ok: "Applies to your van" }[worst];
      box.className = "yours y-" + worst;
      box.innerHTML = "<b>" + label + "</b>"
        + f.map(function (x) { return x[1]; }).join(" ");
    });
    var ok = document.querySelectorAll(".y-ok").length;
    var all = document.querySelectorAll(".yours").length;
    var sum = document.getElementById("v-summary");
    if (sum && all) sum.textContent = ok + " of " + all + " records here apply to your van as described.";
  }

  function bind(id, key, kind) {
    var el = document.getElementById(id);
    if (!el) return;
    if (kind === "bool") el.checked = d[key]; else el.value = d[key];
    el.addEventListener("change", function () {
      d[key] = kind === "bool" ? el.checked
             : kind === "num" ? parseFloat(el.value) : el.value;
      try { localStorage.setItem(K, JSON.stringify(d)); } catch (e) {}
      apply();
    });
  }

  bind("v-height", "height", "num");
  bind("v-length", "length", "num");
  bind("v-body", "body", "str");
  bind("v-toilet", "toilet", "str");
  bind("v-sleeps", "sleeps", "bool");
  bind("v-grey", "grey", "bool");
  bind("v-black", "black", "bool");
  apply();
})();
