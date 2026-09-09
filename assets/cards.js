/* arXivly-atlas — card-level UI: expand / collapse every abstract at once.
   The paper title is a plain heading link outside the <details>, so no
   click-through juggling is needed here. */
(function () {
  "use strict";

  function setAll(open) {
    var list = document.querySelectorAll("details.paper-more");
    for (var i = 0; i < list.length; i++) list[i].open = open;
  }

  var expand = document.querySelector(".expand-all");
  var collapse = document.querySelector(".collapse-all");
  if (expand) expand.addEventListener("click", function () { setAll(true); });
  if (collapse) collapse.addEventListener("click", function () { setAll(false); });
})();
