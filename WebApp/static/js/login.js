function showTab(tab) {
    // Nasconde tutti i form
    document.querySelectorAll('.form-container').forEach(container => {
        container.classList.remove('active');
    });

    // Rimuove classe active da tutti i tab
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Mostra il form selezionato
    document.getElementById(tab + '-form').classList.add('active');

    // Attiva il tab corrente
    event.target.classList.add('active');
}

// Validazione form cambio credenziali
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('change-form').addEventListener('submit', function(e) {
        const newPassword = document.getElementById('new_password').value;
        const confirmPassword = document.getElementById('confirm_password').value;
        const newUsername = document.getElementById('new_username').value;

        // Se sta cambiando password, deve confermarla
        if (newPassword && newPassword !== confirmPassword) {
            e.preventDefault();
            alert('Le password non coincidono!');
            return;
        }

        // Deve cambiare almeno qualcosa
        if (!newPassword && !newUsername) {
            e.preventDefault();
            alert('Devi fornire almeno un nuovo username o una nuova password!');
            return;
        }
    });
});
