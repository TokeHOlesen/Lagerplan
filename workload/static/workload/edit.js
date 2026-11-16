// "+ Tilføj serie": adds an empty row to a day's formset.
document.querySelectorAll("[data-add-row]").forEach((button) => {
  button.addEventListener("click", () => {
    const prefix = button.dataset.addRow;
    const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const template = document.getElementById(`tpl-${prefix}`);
    const rows = document.getElementById(`rows-${prefix}`);
    const index = parseInt(total.value, 10);
    rows.insertAdjacentHTML("beforeend", template.innerHTML.replace(/__prefix__/g, String(index)));
    total.value = String(index + 1);
    const select = rows.lastElementChild && rows.lastElementChild.querySelector("select");
    if (select) select.focus();
  });
});
