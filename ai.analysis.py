import os
import json
import logging
import base64
import io
from datetime import datetime
from typing import Dict, List, Optional, Union
from telethon import events
import mplfinance as mpf
import pandas as pd
import numpy as np

from api.telegram import TelegramAPI
from api.openai import OpenaiAPI, OpenAIError, AnalysisError, ImageProcessingError
from api.mexc import MexcAPI
from api.technical.analysis import TechnicalAnalysis as TA

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info

class TechnicalAnalysis:
    def __init__(
        self,
        telegram_api: TelegramAPI,
        openai_api: OpenaiAPI,
        mexc_api: MexcAPI,
        channels: Dict[str, Dict],
        DEBUG: bool = False
    ):
        self.__telegram_api = telegram_api
        self.__openai_api = openai_api
        self.__mexc_api = mexc_api
        self.__channels = channels
        self.__DEBUG = DEBUG
        self.__ta = TA()

    def _prepare_klines_data(self, klines: List[Dict]) -> pd.DataFrame:
        """
        Przygotowuje dane świeczek do formatu wymaganego przez mplfinance
        
        Args:
            klines: Lista świeczek z API
            
        Returns:
            DataFrame w formacie wymaganym przez mplfinance
        """
        df = pd.DataFrame(klines)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Konwersja kolumn na float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
            
        return df

    def _generate_technical_chart(self, df: pd.DataFrame, analysis: Dict) -> str:
        """
        Generuje wykres techniczny z wskaźnikami
        
        Args:
            df: DataFrame z danymi świeczek
            analysis: Słownik z analizą
            
        Returns:
            Base64 string z wykresem
        """
        # Obliczanie wskaźników
        rsi = self.__ta.calculate_rsi(df.to_dict('records'))
        macd = self.__ta.calculate_macd(df.to_dict('records'))
        obv = self.__ta.calculate_obv(df.to_dict('records'))
        harmonic_patterns = self.__ta.calculate_harmonic_patterns_with_fibonacci(df.to_dict('records'))
        
        # Przygotowanie dodatkowych paneli
        add_plots = []
        
        # RSI
        rsi_series = pd.Series(rsi, index=df.index[-len(rsi):])
        add_plots.append(mpf.make_addplot(rsi_series, panel=1, color='purple', title='RSI'))
        
        # MACD
        macd_series = pd.Series(macd['macd_line'], index=df.index[-len(macd['macd_line']):])
        signal_series = pd.Series(macd['signal_line'], index=df.index[-len(macd['signal_line']):])
        add_plots.append(mpf.make_addplot(macd_series, panel=2, color='blue', title='MACD'))
        add_plots.append(mpf.make_addplot(signal_series, panel=2, color='red'))
        
        # OBV
        obv_series = pd.Series(obv, index=df.index[-len(obv):])
        add_plots.append(mpf.make_addplot(obv_series, panel=3, color='green', title='OBV'))
        
        # Style wykresu
        style = mpf.make_mpf_style(
            base_mpf_style='charles',
            gridstyle='',
            y_on_right=False,
            marketcolors=mpf.make_marketcolors(
                up='green',
                down='red',
                edge='inherit',
                wick='inherit',
                volume='in'
            )
        )
        
        # Generowanie wykresu
        fig, axes = mpf.plot(
            df,
            type='candle',
            style=style,
            title=f'\n{analysis["asset"]}/{analysis["quote"]} - Analiza Techniczna',
            volume=True,
            addplot=add_plots,
            panel_ratios=(3,1,1,1),
            returnfig=True
        )
        
        # Konwersja do base64
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        
        return img_str

    async def analyze_message(self, message: str, image: Optional[Union[str, bytes]] = None) -> Optional[Dict]:
        """
        Analizuje wiadomość i opcjonalnie obrazek używając OpenAI i zwraca wyniki w formacie JSON
        
        Args:
            message: Wiadomość do analizy
            image: Opcjonalne dane obrazka (ścieżka do pliku, base64 string lub bytes)
            
        Returns:
            Słownik z wynikami analizy lub None w przypadku błędu
        """
        try:
            response = await self.__openai_api.send_message(message, image)
            
            if response and "message" in response:
                try:
                    analysis = json.loads(response["message"])
                    return analysis
                except json.JSONDecodeError as e:
                    logger.error(f"Nie udało się zdekodować odpowiedzi JSON: {e}")
                    return None
            return None

        except AnalysisError as e:
            logger.error(f"Błąd analizy OpenAI: {e}")
            return None
        except ImageProcessingError as e:
            logger.error(f"Błąd przetwarzania obrazka: {e}")
            return None
        except OpenAIError as e:
            logger.error(f"Błąd OpenAI: {e}")
            return None
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas analizy: {e}")
            return None

    async def handle_message(self, event: events.NewMessage.Event) -> None:
        """
        Obsługuje nową wiadomość z kanału Telegram
        
        Args:
            event: Event z nową wiadomością
        """
        try:
            # Sprawdź czy wiadomość pochodzi z monitorowanego kanału
            chat_id = event.chat_id
            if not any(channel["id"] == chat_id for channel in self.__channels.values()):
                return

            # Pobierz obrazek jeśli istnieje
            image = None
            if event.message.media:
                try:
                    # Pobierz obrazek z wiadomości
                    image = await self.__telegram_api.download_media(event.message.media)
                except Exception as e:
                    logger.warning(f"Nie udało się pobrać obrazka z wiadomości: {e}")
                    self.__telegram_api.send_message(f"Nie udało się pobrać obrazka z wiadomości: {e}")

            # Analizuj wiadomość i obrazek
            analysis = await self.analyze_message(event.message.message, image)
            
            if analysis and "asset" in analysis and "quote" in analysis:
                self.__telegram_api.send_message(f"Znaleziono analizę dla {analysis['asset']}/{analysis['quote']}")
                
                if not self.__DEBUG:
                    try:
                        # Pobierz dane świeczek
                        klines = self.__mexc_api._get_klines(
                            symbol=f"{analysis['asset']}{analysis['quote']}",
                            interval=analysis.get('interval', '1h'),
                            limit=analysis.get('limit', 100)
                        )
                        
                        # Przygotuj dane do wykresu
                        df = self._prepare_klines_data(klines)
                        
                        # Wygeneruj wykres techniczny
                        chart_base64 = self._generate_technical_chart(df, analysis)
                        
                        # Wyślij wykres do OpenAI w celu weryfikacji analizy
                        verification = await self.__openai_api.send_message(
                            message=f"Zweryfikuj analizę techniczną dla {analysis['asset']}/{analysis['quote']} na podstawie wykresu:",
                            image=chart_base64
                        )
                        
                        if verification and "message" in verification:
                            self.__telegram_api.send_message(
                                f"Weryfikacja analizy technicznej:\n{verification['message']}"
                            )
                        
                    except Exception as e:
                        logger.error(f"Błąd podczas analizy technicznej: {e}")
                        self.__telegram_api.send_message(f"Wystąpił błąd podczas analizy technicznej: {e}")

        except Exception as error:
            logger.error(f"Błąd podczas obsługi wiadomości: {error}")

    def register_handlers(self) -> None:
        """
        Rejestruje handlery dla wiadomości z monitorowanych kanałów
        """
        for channel_name, channel_info in self.__channels.items():
            self.__telegram_api.add_event_handler(
                self.handle_message,
                events.NewMessage(chats=channel_info["id"])
            ) 