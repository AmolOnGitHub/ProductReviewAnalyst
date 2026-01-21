from __future__ import annotations
import pandas as pd
import plotly.express as px


def plot_nps_by_category(metrics_df: pd.DataFrame):
    df = metrics_df.dropna(subset=["category", "nps"])
    fig = px.bar(df, x="category", y="nps", title="NPS by Category")
    fig.update_layout(xaxis_title="Category", yaxis_title="NPS", xaxis_tickangle=-45)
    return fig


def plot_avg_rating_by_category(metrics_df: pd.DataFrame):
    df = metrics_df.dropna(subset=["category", "avg_rating"])
    fig = px.bar(df, x="category", y="avg_rating", title="Average Rating by Category")
    fig.update_layout(xaxis_title="Category", yaxis_title="Average Rating", xaxis_tickangle=-45)
    return fig


def plot_rating_distribution(df: pd.DataFrame, category: str):
    sub = df[df["category"] == category].copy()
    sub = sub.dropna(subset=["rating"])
    fig = px.histogram(sub, x="rating", nbins=5, title=f"Rating Distribution — {category}")
    fig.update_layout(xaxis_title="Rating", yaxis_title="Count")
    return fig