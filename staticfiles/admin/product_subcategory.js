/**
 * Dynamic Subcategory Filter for Django Admin Product Form
 *
 * When the "category" field changes, this script fetches the
 * subcategories that belong to the selected category via AJAX
 * and updates the "subcategory" dropdown accordingly.
 */
document.addEventListener('DOMContentLoaded', function () {
    // Find the category and subcategory select fields in the admin form
    var categoryField = document.getElementById('id_category');
    var subcategoryField = document.getElementById('id_subcategory');

    if (!categoryField || !subcategoryField) return;

    // Store the initially selected subcategory (for edit forms)
    var initialSubcategory = subcategoryField.value;

    /**
     * Fetch subcategories for a given category ID and populate the dropdown.
     */
    function loadSubcategories(categoryId) {
        if (!categoryId) {
            // No category selected: clear subcategory options
            subcategoryField.innerHTML = '<option value="">---------</option>';
            return;
        }

        // Fetch subcategories via AJAX
        fetch('/ajax/load-subcategories/?category_id=' + encodeURIComponent(categoryId))
            .then(function (response) { return response.json(); })
            .then(function (data) {
                // Clear existing options
                subcategoryField.innerHTML = '<option value="">---------</option>';

                // Populate with new subcategories
                data.forEach(function (sub) {
                    var option = document.createElement('option');
                    option.value = sub.id;
                    option.textContent = sub.name;
                    // Re-select the initial subcategory if editing
                    if (String(sub.id) === String(initialSubcategory)) {
                        option.selected = true;
                    }
                    subcategoryField.appendChild(option);
                });
            })
            .catch(function (err) {
                console.error('Failed to load subcategories:', err);
            });
    }

    // Listen for changes on the category field
    categoryField.addEventListener('change', function () {
        loadSubcategories(this.value);
    });

    // If a category is already selected on page load (edit form), load its subcategories
    if (categoryField.value) {
        loadSubcategories(categoryField.value);
    }
});
