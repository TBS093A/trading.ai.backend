-- Skrypt usuwania tabel związanych z użytkownikami i Telegramem
-- UWAGA: To nieodwracalnie usunie wszystkie dane z tych tabel!

-- Usunięcie tabel w odpowiedniej kolejności (z uwzględnieniem foreign key)

-- 1. Tabele sygnałów Telegram
DROP TABLE IF EXISTS telegram_signal_interpretation CASCADE;
DROP TABLE IF EXISTS telegram_signals CASCADE; 
DROP TABLE IF EXISTS telegram_signal_channels CASCADE;

-- 2. Tabele użytkowników 
DROP TABLE IF EXISTS user_secrets CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Pokaż jakie tabele pozostały w bazie
SELECT tablename 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;

-- Sprawdź czy są jakieś pozostałe foreign key do usuniętych tabel
SELECT 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND (ccu.table_name IN ('users', 'user_secrets', 'telegram_signal_channels', 'telegram_signals', 'telegram_signal_interpretation')
         OR tc.table_name IN ('users', 'user_secrets', 'telegram_signal_channels', 'telegram_signals', 'telegram_signal_interpretation'));
