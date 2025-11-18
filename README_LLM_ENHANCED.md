# LLM-Enhanced 12 Key Takeaways Generator

## Overview

This enhanced version of the 12 Key Takeaways Generator uses Large Language Models (LLMs) to generate natural, athlete-friendly analysis reports. The system processes badminton match data and uses OpenAI's GPT models to create human-readable insights that follow the exact prompt structure specifications.

## Key Features

### 🤖 LLM-Powered Analysis
- **Natural Language Generation**: Uses GPT-4 to create athlete-friendly, readable reports
- **Exact Prompt Structure**: Implements the precise prompt specifications you provided
- **Consistent Tone**: Maintains the same analytical voice across all sections
- **Frame Span Integration**: Automatically includes frame references in parentheses

### 📊 Comprehensive Data Processing
- **7 Analysis Sections**: Each section uses LLM with specific prompts
- **Data Sampling**: Handles large datasets efficiently with intelligent sampling
- **Error Handling**: Graceful fallbacks when data is missing or LLM calls fail
- **Flexible Input**: Works with various CSV file formats and naming conventions

## Installation & Setup

### Prerequisites
```bash
pip install pandas openai
```

### OpenAI API Key Setup
Choose one of these methods:

1. **Environment Variable** (Recommended):
```bash
export OPENAI_API_KEY="your-api-key-here"
```

2. **Command Line Argument**:
```bash
python generate_12_key_takeaways.py --openai_api_key your-api-key-here --match_dir /path/to/match
```

3. **Direct in Code**:
```python
generator = BadmintonAnalysisGenerator(match_dir, openai_api_key="your-key")
```

## Usage

### Basic Usage
```bash
python generate_12_key_takeaways.py --match_dir Akira_vs_Mithra_Semis_1 --output_dir analysis_results
```

### With Custom API Key
```bash
python generate_12_key_takeaways.py --match_dir Akira_vs_Mithra_Semis_1 --openai_api_key sk-... --output_dir analysis_results
```

### Test Without API Key
```bash
python test_llm_analysis.py
```

## System Architecture

### LLM Integration Flow
```
CSV Data → Data Preparation → LLM Prompt → GPT-4 Response → Natural Language Report
```

### Section-Specific Prompts
Each section uses tailored prompts based on your specifications:

1. **Serve-Receive**: Analyzes serve patterns and receive effectiveness
2. **Winning & Losing Shots**: Identifies key shot patterns with frame spans
3. **Rally Momentum**: Examines phase patterns and turning points
4. **Shot Effectiveness**: Detailed effectiveness analysis with serve limitations
5. **Zones**: Zone-based positioning analysis
6. **Top-3s + Turning Points**: Summary analysis (placeholder for enhancement)
7. **Final 12 Takeaways**: Aggregates all sections into exactly 12 highlights

## Output Structure

### Individual Section Files
- `serve_receive.md` - Serve variation analysis
- `winning_losing.md` - Shot effectiveness patterns
- `rally_momentum.md` - Rally flow and turning points
- `shot_effectiveness.md` - Detailed shot analysis
- `zones.md` - Zone positioning insights
- `top3s.md` - Summary analysis
- `final_takeaways.md` - Final 12 key highlights

### Combined Report
- `12_key_takeaways_complete.md` - All sections combined

## Example Output

### Serve Variation Section
```markdown
# Serve Variation
- Your serve variation shows excellent diversity with High Serve as the primary weapon, complemented by strategic Serve Middle placements that keep the opponent guessing
- Opponent relies heavily on High Serve patterns, creating predictable receive opportunities for you to exploit
- Most frequent serve-receive pairs demonstrate your ability to convert High Serve → Forehand Clear combinations effectively (3317-3415, 7202-7304, 19737-19847)
```

### Final 12 Takeaways
```markdown
# Key Takeaways — 12 Highlights

## 1) Things that are working
- Your serve variation creates consistent pressure with High Serve dominating the pattern (53 uses) while mixing in strategic Serve Middle placements
- Strong net play execution in front court positions, particularly with Backhand Net Keep Cross shots that close points effectively (20285, 32159, 32655)
- Effective Reset/Baseline = length to neutral/control patterns that maintain rally control and set up attacking opportunities

## 2) Things that absolutely don't work
- Back court to front court shots consistently result in point-losing positioning, especially Overhead Drop Cross attempts from back court
- Defensive shots from middle court positions lack the necessary power and placement to create offensive opportunities
- Mixed tactical approaches without clear direction lead to inconsistent rally outcomes and missed opportunities

## 3) Things that could be better
- Serve-receive transition consistency could improve, particularly in converting receive opportunities into attacking positions
- Placement = precise positioning under pressure needs refinement, especially in crucial moments of the match
- Net Battle = tape control exchanges require more consistent execution during high-pressure situations

## 4) Mandatory observations
- Serve variation: High serve dominant with good receive options, showing 98 total serves across multiple patterns
- Winners vs Errors: You 23-22, Opponent 24-35 - your positive ratio while opponent struggles with errors
- Most successful zones: Front court positioning for you creates point-winning opportunities, while opponent's back court positioning yields better results
```

## Configuration Options

### LLM Model Selection
```python
# In the call_llm method, you can change the model
def call_llm(self, system_prompt: str, user_prompt: str, model: str = "gpt-4"):
    # Change "gpt-4" to "gpt-3.5-turbo" for faster/cheaper processing
```

### Data Sampling
```python
# For large datasets, sampling is automatic
sample_df = effectiveness_df.sample(min(1000, len(effectiveness_df)))
```

### Temperature Control
```python
# Adjust creativity vs consistency
response = self.openai_client.ChatCompletion.create(
    model=model,
    messages=[...],
    temperature=0.7  # Lower = more consistent, Higher = more creative
)
```

## Error Handling

### Missing Data
- Graceful handling of missing CSV files
- Fallback messages when data is unavailable
- Continues processing with available data

### LLM Errors
- API key validation
- Rate limiting handling
- Network error recovery
- Fallback to error messages when LLM calls fail

### Data Processing
- Safe CSV loading with multiple separator attempts
- Frame range parsing with error recovery
- Shot name conversion with special case handling

## Performance Considerations

### Token Management
- Automatic data sampling for large datasets
- Efficient JSON serialization
- Prompt optimization to stay within token limits

### Cost Optimization
- Uses GPT-4 by default for best quality
- Can switch to GPT-3.5-turbo for cost savings
- Intelligent data sampling reduces token usage

### Processing Speed
- Parallel section generation possible
- Efficient data loading and preparation
- Caching of processed data

## Troubleshooting

### Common Issues

1. **"OpenAI API key not configured"**
   - Set environment variable: `export OPENAI_API_KEY="your-key"`
   - Or pass as argument: `--openai_api_key your-key`

2. **"Error calling LLM"**
   - Check API key validity
   - Verify internet connection
   - Check OpenAI service status

3. **"Data not available"**
   - Ensure CSV files exist in match directory
   - Check file naming conventions
   - Verify file permissions

4. **Empty or incomplete output**
   - Check data quality in CSV files
   - Verify column names match expected format
   - Review error messages in console

### Debug Mode
```python
# Add debug prints to see data flow
generator = BadmintonAnalysisGenerator(match_dir, openai_api_key)
print("Debug: Data loaded successfully")
sections = generator.generate_all_sections()
```

## Future Enhancements

### Planned Features
1. **Multi-Model Support**: Integration with other LLM providers
2. **Custom Prompts**: User-defined prompt templates
3. **Interactive Reports**: HTML output with interactive elements
4. **Real-time Analysis**: Live match data processing
5. **Comparative Analysis**: Multi-match comparison capabilities

### Extension Points
- Add new analysis sections easily
- Custom data processors for different file formats
- Integration with video analysis tools
- Export to various formats (PDF, HTML, etc.)

## Contributing

### Adding New Sections
1. Create new method: `def section_X_new_analysis(self) -> str:`
2. Add LLM prompt following the established pattern
3. Update `generate_all_sections()` method
4. Test with sample data

### Custom Data Processors
1. Extend `load_csv_safely()` method
2. Add data validation and cleaning
3. Implement custom frame parsing if needed
4. Update error handling

## License

This project follows the same license as the parent Match Analysis Engine.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review error messages in console output
3. Test with `test_llm_analysis.py` for data validation
4. Verify API key and data file availability

---

**Note**: This system requires an active OpenAI API key and internet connection for full functionality. The test script can be used to verify data preparation without API calls.

