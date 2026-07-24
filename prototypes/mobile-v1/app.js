const dayButtons = document.querySelectorAll(".day");
const agendaDate = document.querySelector(".agendaHeader strong");

dayButtons.forEach((button) => {
  button.addEventListener("click", () => {
    dayButtons.forEach((item) => item.classList.remove("selected"));
    button.classList.add("selected");
    if (agendaDate && !button.classList.contains("muted")) {
      agendaDate.textContent = `Jul ${button.textContent.trim()}`;
    }
  });
});

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segmented button").forEach((item) => {
      item.classList.remove("active");
      item.setAttribute("aria-selected", "false");
    });
    button.classList.add("active");
    button.setAttribute("aria-selected", "true");
  });
});

document.querySelectorAll(".checkButton").forEach((button) => {
  button.addEventListener("click", () => {
    button.classList.toggle("checked");
    button.closest(".taskRow")?.classList.toggle("done");
  });
});
