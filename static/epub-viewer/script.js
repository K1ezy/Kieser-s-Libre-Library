// Get the book URL from the browser address bar
const urlParams = new URLSearchParams(window.location.search);
const bookUrl = urlParams.get('file');

if (bookUrl) {
    // Initialize ePub.js
    const book = ePub(bookUrl);
    
    const rendition = book.renderTo("viewer", {
        width: "100%",
        height: "100%",
        flow: "paginated"
    });

    rendition.display();

    // Hook up the buttons
    document.getElementById("next").addEventListener("click", () => rendition.next());
    document.getElementById("prev").addEventListener("click", () => rendition.prev());

    // Add keyboard support (Left/Right arrows)
    document.addEventListener("keyup", function(e) {
        if (e.key === "ArrowLeft") rendition.prev();
        if (e.key === "ArrowRight") rendition.next();
    });
} else {
    document.getElementById("viewer").innerText = "Error: No book file specified in URL.";
}