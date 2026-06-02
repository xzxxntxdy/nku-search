const searchBox = document.querySelector("#searchBox");
const suggestions = document.querySelector("#suggestions");

async function refreshSuggestions(value) {
  if (!searchBox || !suggestions || value.trim().length === 0) {
    if (suggestions) suggestions.style.display = "none";
    return;
  }
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(value.trim())}`);
  if (!response.ok) return;
  const data = await response.json();
  suggestions.innerHTML = "";
  for (const item of data.suggestions || []) {
    const link = document.createElement("a");
    link.href = `/search?q=${encodeURIComponent(item)}`;
    link.textContent = item;
    suggestions.appendChild(link);
  }
  suggestions.style.display = suggestions.children.length ? "block" : "none";
}

if (searchBox && suggestions) {
  searchBox.addEventListener("input", (event) => {
    refreshSuggestions(event.target.value);
  });
  document.addEventListener("click", (event) => {
    if (!suggestions.contains(event.target) && event.target !== searchBox) {
      suggestions.style.display = "none";
    }
  });
}

