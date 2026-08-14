using System.Globalization;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenAlgo.NET;

internal sealed class NumberOrStringConverter : JsonConverter<string>
{
    public override string? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        return reader.TokenType switch
        {
            JsonTokenType.String => reader.GetString(),
            JsonTokenType.Number => reader.GetDecimal().ToString(CultureInfo.InvariantCulture),
            JsonTokenType.Null => null,
            _ => throw new JsonException($"Expected a string or number but found {reader.TokenType}.")
        };
    }

    public override void Write(Utf8JsonWriter writer, string? value, JsonSerializerOptions options)
    {
        if (value == null)
        {
            writer.WriteNullValue();
            return;
        }

        writer.WriteStringValue(value);
    }
}

/// <summary>
/// Custom snake_case naming policy for JSON serialization (compatible with .NET 6/7/8).
/// </summary>
internal sealed class SnakeCaseNamingPolicy : JsonNamingPolicy
{
    public static SnakeCaseNamingPolicy Instance { get; } = new();

    public override string ConvertName(string name)
    {
        if (string.IsNullOrEmpty(name))
            return name;

        var builder = new StringBuilder();
        for (int i = 0; i < name.Length; i++)
        {
            var c = name[i];
            if (char.IsUpper(c))
            {
                if (i > 0)
                    builder.Append('_');
                builder.Append(char.ToLowerInvariant(c));
            }
            else
            {
                builder.Append(c);
            }
        }
        return builder.ToString();
    }
}

/// <summary>
/// Base API class providing HTTP client infrastructure for all API operations.
/// </summary>
public abstract class BaseApi
{
    /// <summary>
    /// The API key for authentication.
    /// </summary>
    protected readonly string ApiKey;

    /// <summary>
    /// The base URL for API requests.
    /// </summary>
    protected readonly string BaseUrl;

    /// <summary>
    /// HTTP client for making requests.
    /// </summary>
    protected readonly HttpClient HttpClient;

    /// <summary>
    /// JSON serializer options.
    /// </summary>
    protected static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = SnakeCaseNamingPolicy.Instance,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false
    };

    static BaseApi()
    {
        JsonOptions.Converters.Add(new NumberOrStringConverter());
    }

    /// <summary>
    /// Initializes a new instance of the BaseApi class.
    /// </summary>
    /// <param name="apiKey">The API key for authentication.</param>
    /// <param name="host">The host URL of the OpenAlgo server.</param>
    /// <param name="version">The API version.</param>
    /// <param name="timeout">Request timeout in seconds.</param>
    protected BaseApi(string apiKey, string host = "http://127.0.0.1:5000", string version = "v1", double timeout = 120.0)
    {
        ApiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
        BaseUrl = $"{host.TrimEnd('/')}/api/{version}/";

        HttpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(timeout)
        };
        HttpClient.DefaultRequestHeaders.Add("Accept", "application/json");
    }

    /// <summary>
    /// Makes an async POST request to the specified endpoint.
    /// </summary>
    /// <typeparam name="TResponse">The response type.</typeparam>
    /// <param name="endpoint">The API endpoint.</param>
    /// <param name="payload">The request payload.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The deserialized response.</returns>
    protected async Task<TResponse> MakeRequestAsync<TResponse>(string endpoint, object payload, CancellationToken cancellationToken = default)
        where TResponse : class, new()
    {
        var url = BaseUrl + endpoint;

        try
        {
            var response = await HttpClient.PostAsJsonAsync(url, payload, JsonOptions, cancellationToken);
            return await HandleResponseAsync<TResponse>(response, cancellationToken);
        }
        catch (TaskCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (TaskCanceledException)
        {
            return CreateErrorResponse<TResponse>("Request timed out. Please check your connection and try again.", "timeout_error");
        }
        catch (HttpRequestException ex)
        {
            return CreateErrorResponse<TResponse>($"Connection error: {ex.Message}", "connection_error");
        }
        catch (Exception ex)
        {
            return CreateErrorResponse<TResponse>($"Unexpected error: {ex.Message}", "unknown_error");
        }
    }

    /// <summary>
    /// Makes a sync POST request to the specified endpoint.
    /// </summary>
    /// <typeparam name="TResponse">The response type.</typeparam>
    /// <param name="endpoint">The API endpoint.</param>
    /// <param name="payload">The request payload.</param>
    /// <returns>The deserialized response.</returns>
    protected TResponse MakeRequest<TResponse>(string endpoint, object payload)
        where TResponse : class, new()
    {
        return MakeRequestAsync<TResponse>(endpoint, payload).GetAwaiter().GetResult();
    }

    /// <summary>
    /// Handles the HTTP response and deserializes it.
    /// </summary>
    private async Task<TResponse> HandleResponseAsync<TResponse>(HttpResponseMessage response, CancellationToken cancellationToken)
        where TResponse : class, new()
    {
        try
        {
            var content = await response.Content.ReadAsStringAsync(cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                return CreateErrorResponse<TResponse>($"HTTP {(int)response.StatusCode}: {content}", "http_error", (int)response.StatusCode);
            }

            var result = JsonSerializer.Deserialize<TResponse>(content, JsonOptions);
            if (result == null)
            {
                return CreateErrorResponse<TResponse>("Empty response from server", "empty_response");
            }

            return result;
        }
        catch (JsonException ex)
        {
            return CreateErrorResponse<TResponse>($"Invalid JSON response: {ex.Message}", "json_error");
        }
    }

    /// <summary>
    /// Creates an error response object.
    /// </summary>
    private static TResponse CreateErrorResponse<TResponse>(string message, string errorType, int? code = null)
        where TResponse : class, new()
    {
        var response = new TResponse();

        // Try to set Status property
        var statusProperty = typeof(TResponse).GetProperty("Status");
        statusProperty?.SetValue(response, "error");

        // Try to set Message property
        var messageProperty = typeof(TResponse).GetProperty("Message");
        messageProperty?.SetValue(response, message);

        // Try to set ErrorType property
        var errorTypeProperty = typeof(TResponse).GetProperty("ErrorType");
        errorTypeProperty?.SetValue(response, errorType);

        // Try to set Code property
        if (code.HasValue)
        {
            var codeProperty = typeof(TResponse).GetProperty("Code");
            codeProperty?.SetValue(response, code.Value);
        }

        return response;
    }

    /// <summary>
    /// Creates a payload dictionary with the API key.
    /// </summary>
    protected Dictionary<string, object?> CreatePayload()
    {
        return new Dictionary<string, object?>
        {
            ["apikey"] = ApiKey
        };
    }

    /// <summary>
    /// Adds a value to the payload if it's not null.
    /// </summary>
    protected static void AddIfNotNull(Dictionary<string, object?> payload, string key, object? value)
    {
        if (value != null)
        {
            // Convert numbers to strings as required by the Python API
            payload[key] = value is int or long or double or float or decimal
                ? value.ToString()
                : value;
        }
    }
}
