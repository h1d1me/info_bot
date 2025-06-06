@echo off
echo 🔄 Wysyłanie zmian na VPS...
pscp -P 2022 C:\nocna_up\* root@194.110.4.124:/root/t1/info_bot/

echo 🔁 Restart bota...
plink -P 2022 root@194.110.4.124 "source /root/t1/bin/activate && pkill -f info_bot.py && screen -dmS bot python /root/t1/info_bot/info_bot.py"

echo ✅ Gotowe! Bot został zaktualizowany.
pause
