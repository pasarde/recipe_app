document.addEventListener('DOMContentLoaded', () => {
    const csrftoken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    // Handle Like and Save Buttons
    const likeButtons = document.querySelectorAll('.like-btn');
    const saveButtons = document.querySelectorAll('.save-btn');
    const interactError = document.getElementById('interact-error');

    const handleInteract = async (button, action) => {
        const source = button.getAttribute('data-source');
        const recipeId = button.getAttribute('data-recipe-id');
        const formData = new FormData();
        formData.append('source', source);
        formData.append('recipe_id', recipeId);
        formData.append('action', action);

        // Disable button to prevent double-click
        button.disabled = true;
        if (interactError) interactError.classList.add('d-none');

        try {
            const response = await fetch('/interact', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRF-Token': csrftoken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Update Like Button
            if (action === 'like') {
                const likeText = button.querySelector('.like-text');
                const likeCount = button.querySelector('.like-count');
                likeText.textContent = data.user_liked ? 'Unlike' : 'Like';
                likeCount.textContent = data.likes;
                button.setAttribute('data-liked', data.user_liked);
            }

            // Update Save Button
            if (action === 'save') {
                const saveText = button.querySelector('.save-text');
                const saveCount = button.querySelector('.save-count');
                saveText.textContent = data.user_saved ? 'Unsave' : 'Save';
                saveCount.textContent = data.saves;
                button.setAttribute('data-saved', data.user_saved);
            }
        } catch (error) {
            if (interactError) {
                interactError.classList.remove('d-none');
                interactError.textContent = error.message;
            }
        } finally {
            button.disabled = false;
        }
    };

    likeButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            handleInteract(button, 'like');
        });
    });

    saveButtons.forEach(button => {
        button.addEventListener('submit', (e) => {
            e.preventDefault();
            handleInteract(button, 'save');
        });
    });
});