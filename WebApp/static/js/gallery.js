function viewFullImage(filename) {
    const modal = document.getElementById('imageModal');
    const modalImage = document.getElementById('modalImage');

    modalImage.src = '/saved_images/' + filename;
    modal.style.display = 'block';

    console.log('Opening full image:', filename);
}

function closeModal() {
    document.getElementById('imageModal').style.display = 'none';
}

// Close modal with Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

console.log('🖼️ Gallery loaded with {{ images|length }} images');