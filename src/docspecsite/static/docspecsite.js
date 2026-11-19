// Version picker: open the chosen version (values are page-relative URLs).
for (const picker of document.querySelectorAll("select.version-picker")) {
  picker.addEventListener("change", () => {
    location.href = picker.value;
  });
}
